"""HTTP integration checks with a real API process and a disposable MySQL database."""
import http.cookiejar
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
import sys

import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/data_loader"))
from main import connection_options

TEST_PASSWORD = "SyntheticManagerPassword-123"
KALPI_PASSWORD = "SyntheticKalpiPassword-456"


class Client:
    def __init__(self, base):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.token = None

    def request(self, path, body=None, csrf=True):
        headers = {"Content-Type": "application/json"}
        if body is not None and csrf and self.token:
            headers["X-CSRF-TOKEN"] = self.token
        request = urllib.request.Request(self.base + path, headers=headers,
                                         data=None if body is None else json.dumps(body).encode("utf-8"))
        try: response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error: response = error
        with response:
            text = response.read().decode("utf-8")
            try: data = json.loads(text)
            except json.JSONDecodeError: data = text
            return response.status, data, response.headers

    def csrf(self):
        status, data, _ = self.request("/api/auth/csrf")
        if status != 200: raise AssertionError("CSRF token request failed")
        self.token = data["token"]

    def login(self, identifier="manager@example.test", password=TEST_PASSWORD):
        self.csrf()
        result = self.request("/api/auth/login", {"identifier": identifier, "password": password})
        if result[0] == 200: self.csrf()
        return result


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "KalpiTechAuthTest_" + uuid.uuid4().hex
        settings = dict(line.split("=", 1) for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
                        if "=" in line and not line.startswith("#"))
        cls.options = connection_options()
        cls.options.update(user="root", password=settings["MYSQL_ROOT_PASSWORD"])
        cls.admin_connection = pymysql.connect(**cls.options)
        with cls.admin_connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{cls.database}` CHARACTER SET utf8mb4")
        cls.addClassCleanup(cls.clean_database)
        cls.options["database"] = cls.database
        cls.connection = pymysql.connect(**cls.options)
        cls.addClassCleanup(cls.connection.close)
        with cls.connection.cursor() as cursor:
            for path in sorted((ROOT / "src/KalpiTech.Api/Data/Sql").glob("*.sql")):
                for statement in path.read_text(encoding="utf-8").split(";"):
                    if statement.strip(): cursor.execute(statement)
            cursor.execute("INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address) VALUES (1,'Regular','a','b','c'),(2,'Accessible','a','b','c'),(3,'Regular','a','b','c')")
        cls.connection.commit()
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.log = open(Path(cls.temp.name) / "api.log", "w", encoding="utf-8")
        cls.addClassCleanup(cls.log.close)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(MYSQL_USER="root", MYSQL_PASSWORD=settings["MYSQL_ROOT_PASSWORD"], MYSQL_DATABASE=cls.database,
                   ADMIN_EMAIL="manager@example.test", ADMIN_INITIAL_PASSWORD=TEST_PASSWORD,
                   DataProtection__KeyPath=str(Path(cls.temp.name) / "keys"))
        cls.env = env
        cls.start_process()
        cls.addClassCleanup(cls.stop_process)
        with cls.connection.cursor() as cursor:
            cursor.execute("SELECT PasswordHash FROM AdminAccount WHERE Id=1")
            cls.initial_hash = cursor.fetchone()[0]
        cls.connection.commit()

    @classmethod
    def start_process(cls):
        cls.process = subprocess.Popen(["dotnet", str(ROOT / ".local/stage04-build/KalpiTech.Api.dll"), "--urls", cls.base],
                                       cwd=ROOT / "src/KalpiTech.Api", env=cls.env, stdout=cls.log, stderr=cls.log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for _ in range(100):
            if cls.process.poll() is not None: raise RuntimeError("Test API exited during startup")
            try:
                if Client(cls.base).request("/health")[0] == 200: break
            except (OSError, urllib.error.URLError): time.sleep(.1)
        else: raise RuntimeError("Test API did not start")

    @classmethod
    def stop_process(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)

    @classmethod
    def clean_database(cls):
        with cls.admin_connection.cursor() as cursor: cursor.execute(f"DROP DATABASE `{cls.database}`")
        cls.admin_connection.close()

    def setUp(self):
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE AdminAccount SET PasswordHash=%s WHERE Id=1", (self.initial_hash,))
            cursor.execute("UPDATE Kalpi SET PasswordHash=NULL")
        self.connection.commit()
        self.client = Client(self.base)

    def admin(self):
        self.assertEqual(self.client.login()[0], 200)

    def set_station(self, station=1, password=KALPI_PASSWORD):
        return self.client.request("/api/auth/kalpi-password", {"kalpiId": station, "newPassword": password})

    def test_anonymous_is_401_and_password_api_is_protected(self):
        self.assertEqual(self.client.request("/api/auth/me")[0], 401)
        self.client.csrf()
        self.assertEqual(self.set_station()[0], 401)

    def test_wrong_login_and_station_without_password(self):
        self.assertEqual(self.client.login(password="wrong")[0], 401)
        self.assertEqual(self.client.login("3", KALPI_PASSWORD)[0], 401)

    def test_admin_login_cookie_and_current_account(self):
        self.admin()
        status, account, headers = self.client.request("/api/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(account, {"identifier": "manager@example.test", "role": "Admin", "kalpiId": None})
        self.assertEqual(headers["Cache-Control"], "no-store")
        auth_cookie = next(cookie for cookie in self.client.cookies if cookie.name == "KalpiTech.Auth")
        self.assertTrue(any(key.lower() == "httponly" for key in auth_cookie._rest))
        self.assertNotIn(TEST_PASSWORD, auth_cookie.value)
        self.assertNotEqual(self.initial_hash, TEST_PASSWORD)

    def test_csrf_is_required_for_login_and_password_change(self):
        self.assertEqual(self.client.request("/api/auth/login", {"identifier": "manager@example.test", "password": TEST_PASSWORD}, csrf=False)[0], 400)
        self.admin()
        self.assertEqual(self.client.request("/api/auth/kalpi-password", {"kalpiId": 1, "newPassword": KALPI_PASSWORD}, csrf=False)[0], 400)

    def test_regular_and_accessible_roles_come_from_database(self):
        self.admin()
        for station, role in ((1, "Regular"), (2, "Accessible")):
            self.assertEqual(self.set_station(station)[0], 200)
            client = Client(self.base)
            status, account, _ = client.login(str(station), KALPI_PASSWORD)
            self.assertEqual(status, 200)
            self.assertEqual(account["role"], role)
            self.assertEqual(account["kalpiId"], station)
            self.assertEqual(client.request("/api/auth/kalpi-password", {"kalpiId": 3, "newPassword": KALPI_PASSWORD})[0], 403)
            self.assertEqual(client.request("/api/auth/admin-password", {"currentPassword": TEST_PASSWORD, "newPassword": KALPI_PASSWORD})[0], 403)

    def test_short_password_and_missing_station(self):
        self.admin()
        self.assertEqual(self.set_station(password="short")[0], 400)
        self.assertEqual(self.set_station(station=99)[0], 404)

    def test_admin_change_requires_current_password_and_invalidates_old_sessions(self):
        self.admin()
        other = Client(self.base)
        self.assertEqual(other.login()[0], 200)
        self.assertEqual(self.client.request("/api/auth/admin-password", {"currentPassword": "wrong", "newPassword": KALPI_PASSWORD})[0], 400)
        self.assertEqual(self.client.request("/api/auth/admin-password", {"currentPassword": TEST_PASSWORD, "newPassword": KALPI_PASSWORD})[0], 200)
        self.assertEqual(self.client.request("/api/auth/me")[0], 401)
        self.assertEqual(other.request("/api/auth/me")[0], 401)
        self.assertEqual(Client(self.base).login(password=TEST_PASSWORD)[0], 401)
        self.assertEqual(Client(self.base).login(password=KALPI_PASSWORD)[0], 200)

    def test_station_password_change_invalidates_existing_cookie(self):
        self.admin()
        self.assertEqual(self.set_station()[0], 200)
        station_client = Client(self.base)
        self.assertEqual(station_client.login("1", KALPI_PASSWORD)[0], 200)
        self.assertEqual(self.set_station(password="DifferentStationPassword-789")[0], 200)
        self.assertEqual(station_client.request("/api/auth/me")[0], 401)
        self.assertEqual(Client(self.base).login("1", KALPI_PASSWORD)[0], 401)

    def test_logout_ends_browser_login(self):
        self.admin()
        self.assertEqual(self.client.request("/api/auth/logout", {})[0], 200)
        self.assertEqual(self.client.request("/api/auth/me")[0], 401)

    def test_html_and_static_assets_are_served(self):
        for path in ("/", "/css/site.css", "/js/app.js"):
            self.assertEqual(self.client.request(path)[0], 200)

    def test_forged_cookie_is_rejected(self):
        self.admin()
        cookie = next(cookie for cookie in self.client.cookies if cookie.name == "KalpiTech.Auth")
        cookie.value = "forged-cookie"
        self.assertEqual(self.client.request("/api/auth/me")[0], 401)

    def test_restart_preserves_changed_password_and_cookie(self):
        self.admin()
        self.assertEqual(self.client.request("/api/auth/admin-password", {"currentPassword": TEST_PASSWORD, "newPassword": KALPI_PASSWORD})[0], 200)
        self.assertEqual(self.client.login(password=KALPI_PASSWORD)[0], 200)
        self.stop_process()
        type(self).start_process()
        self.assertEqual(self.client.request("/api/auth/me")[0], 200)
        self.assertEqual(Client(self.base).login(password=TEST_PASSWORD)[0], 401)
        self.assertEqual(Client(self.base).login(password=KALPI_PASSWORD)[0], 200)


if __name__ == "__main__": unittest.main()
