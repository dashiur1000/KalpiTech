"""Real MySQL tests in a separate disposable database; run explicitly."""

import csv
import sys
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/data_loader"))
from database import bootstrap
from main import connection_options
from validation import KALPI_COLUMNS, PEOPLE_COLUMNS, ValidationError


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "KalpiTechLoaderTest_" + uuid.uuid4().hex
        settings = dict(line.split("=", 1) for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
                        if "=" in line and not line.startswith("#"))
        cls.options = connection_options()
        cls.options.update(user="root", password=settings["MYSQL_ROOT_PASSWORD"])
        cls.admin = pymysql.connect(**cls.options)
        with cls.admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{cls.name}` CHARACTER SET utf8mb4")
        cls.addClassCleanup(cls.cleanup_database)
        cls.options["database"] = cls.name
        with pymysql.connect(**cls.options) as connection:
            with connection.cursor() as cursor:
                schema = (ROOT / "src/KalpiTech.Api/Data/Sql/001_initial_schema.sql").read_text(encoding="utf-8")
                for statement in schema.split(";"):
                    if statement.strip(): cursor.execute(statement)
            connection.commit()

    @classmethod
    def cleanup_database(cls):
        with cls.admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{cls.name}`")
        cls.admin.close()

    def setUp(self):
        self.connection = pymysql.connect(**self.options)
        self.addCleanup(self.connection.close)
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM People")
            cursor.execute("DELETE FROM Kalpi")
            cursor.execute("UPDATE ElectionSettings SET StartsAt=NULL,EndsAt=NULL WHERE Id=1")
        self.connection.commit()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        with (self.path / "kalpi.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=sorted(KALPI_COLUMNS))
            writer.writeheader()
            writer.writerow(dict(KalpiId="1", KalpiType="Regular", City="בית שמש", Place="ספרייה",
                                 Address="כתובת", PasswordHash="ignore-this"))
        with (self.path / "people.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=sorted(PEOPLE_COLUMNS))
            writer.writeheader()
            writer.writerow(dict(Id="001234567", KalpiId="1", FirstName="יוסף", LastName="אברג'יל",
                                 Voted="FALSE", EmailAddress="", VotedAt="", VotedIn=""))

    def load(self, connection=None, directory=None):
        path = directory or self.path
        return bootstrap(connection or self.connection, path / "kalpi.csv", path / "people.csv")

    def query(self, sql):
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
        self.connection.commit()
        return rows

    def test_load_and_defaults(self):
        self.assertEqual(self.load(), ("loaded", 1, 1))
        self.assertEqual(self.query("SELECT Id,LastName,Voted,EmailAddress,VotedAt,VotedIn FROM People"),
                         (("001234567", "אברג'יל", 0, None, None, None),))
        self.assertEqual(self.query("SELECT PasswordHash FROM Kalpi"), ((None,),))

    def test_existing_votes_passwords_schedule_survive_missing_sources(self):
        self.load()
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE People SET Voted=TRUE,VotedAt='2026-10-10 12:00:00',VotedIn=1")
            cursor.execute("UPDATE Kalpi SET PasswordHash='synthetic-test-hash'")
            cursor.execute("UPDATE ElectionSettings SET StartsAt='2026-10-10 06:00:00',EndsAt='2026-10-10 19:00:00'")
        self.connection.commit()
        before = [self.query("SELECT * FROM " + table) for table in ("People", "Kalpi", "ElectionSettings")]
        with pymysql.connect(**self.options) as fresh_connection:
            self.assertEqual(self.load(fresh_connection, self.path / "missing"), ("existing", 1, 1))
        after = [self.query("SELECT * FROM " + table) for table in ("People", "Kalpi", "ElectionSettings")]
        self.assertEqual(before, after)

    def test_invalid_second_file_writes_nothing(self):
        (self.path / "people.csv").write_text("bad,header\n1,2\n", encoding="utf-8")
        with self.assertRaises(ValidationError): self.load()
        self.assertEqual(self.query("SELECT COUNT(*) FROM Kalpi"), ((0,),))
        self.assertEqual(self.query("SELECT COUNT(*) FROM People"), ((0,),))

    def test_database_failure_rolls_back_station_inserts(self):
        self.query("CREATE TRIGGER RejectTestPerson BEFORE INSERT ON People FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        try:
            with self.assertRaises(pymysql.MySQLError): self.load()
            self.assertEqual(self.query("SELECT COUNT(*) FROM Kalpi"), ((0,),))
            self.assertEqual(self.query("SELECT COUNT(*) FROM People"), ((0,),))
        finally:
            self.query("DROP TRIGGER RejectTestPerson")

    def test_partial_database_stops_without_changes(self):
        self.query("INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address) VALUES (1,'Regular','a','b','c')")
        with self.assertRaises(ValidationError): self.load()
        self.assertEqual(self.query("SELECT COUNT(*) FROM Kalpi"), ((1,),))
        self.assertEqual(self.query("SELECT COUNT(*) FROM People"), ((0,),))

    def test_empty_database_after_election_start_is_not_loaded(self):
        self.query("UPDATE ElectionSettings SET StartsAt='2000-01-01',EndsAt='2000-01-02'")
        with self.assertRaises(ValidationError): self.load()
        self.assertEqual(self.query("SELECT COUNT(*) FROM Kalpi"), ((0,),))

    def test_simultaneous_startup_loads_only_once(self):
        barrier = threading.Barrier(2)
        def run():
            with pymysql.connect(**self.options) as connection:
                barrier.wait(timeout=10)
                return self.load(connection)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=30) for f in futures), ["existing", "loaded"])
        self.assertEqual(self.query("SELECT COUNT(*) FROM People"), ((1,),))


if __name__ == "__main__":
    unittest.main()
