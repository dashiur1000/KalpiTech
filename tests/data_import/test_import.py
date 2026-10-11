"""Real HTTP uploads into disposable MySQL; all earlier API regressions included."""
import csv
import io
import json
import sys
import urllib.error
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor
import pymysql
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/password_csv'))
import test_password_csv as previous


class ImportTests(previous.PasswordCsvTests):
    build_directory = '.local/stage08-build'

    def setUp(self):
        with self.connection.cursor() as cursor:
            cursor.execute('DELETE FROM People')
            cursor.execute('DELETE FROM Kalpi')
            cursor.execute('DELETE FROM DataImportState')
            cursor.execute("INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address) VALUES (1,'Regular','a','b','c'),(2,'Accessible','a','b','c'),(3,'Regular','a','b','c')")
        self.connection.commit()
        super().setUp()

    def files(self, invalid=False):
        def encode(rows):
            output = io.StringIO(newline='')
            csv.writer(output).writerows(rows)
            return output.getvalue().encode('utf-8-sig')
        return (encode([['KalpiId','City','Place','Address','KalpiType','PasswordHash'],
                        [1,'עיר חדשה','מקום, חדש','כתובת','Accessible','SyntheticUploadedPassword-123']]),
                encode([['Id','KalpiId','FirstName','LastName','Voted','EmailAddress','VotedAt','VotedIn'],
                        ['123' if invalid else '000000009',1,'שם','בדיקה','FALSE','','','']]))

    def upload(self, client=None, invalid=False, confirmed=True, csrf=True, files=None):
        client = client or self.client
        boundary = 'KalpiTechSyntheticUploadBoundary'
        content = bytearray()
        for name, data in zip(('kalpiFile','peopleFile'), files or self.files(invalid)):
            content.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="input.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode())
            content.extend(data)
            content.extend(b'\r\n')
        content.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="confirmed"\r\n\r\n{str(confirmed).lower()}\r\n--{boundary}--\r\n'.encode())
        headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
        if csrf and client.token: headers['X-CSRF-TOKEN'] = client.token
        request = urllib.request.Request(self.base+'/api/data/import', data=bytes(content), headers=headers)
        try: response = client.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error: response = error
        with response:
            body = response.read()
            return response.status, json.loads(body) if body else {}

    def empty_votes(self):
        with self.connection.cursor() as cursor:
            cursor.execute('UPDATE People SET Voted=FALSE,VotedAt=NULL,VotedIn=NULL')
        self.connection.commit()

    def snapshot(self):
        self.connection.commit()
        with self.connection.cursor() as cursor:
            result = []
            for table in ('People','Kalpi','ElectionSettings','AdminAccount','DataImportState'):
                cursor.execute(f'SELECT * FROM {table} ORDER BY 1')
                result.append(cursor.fetchall())
        self.connection.commit()
        return result

    def test_upload_requires_admin_csrf_and_confirmation(self):
        self.client.csrf()
        self.assertEqual(self.upload()[0],401)
        poll = self.polling_client()
        self.assertEqual(self.upload(poll)[0],403)
        self.admin()
        self.assertEqual(self.upload(csrf=False)[0],400)
        self.assertEqual(self.upload(confirmed=False)[0],400)

    def test_invalid_files_preserve_every_table(self):
        self.admin()
        self.empty_votes()
        before = self.snapshot()
        self.assertEqual(self.upload(invalid=True)[0],400)
        self.assertEqual(self.snapshot(),before)
        kalpi, people = self.files()
        self.assertEqual(self.upload(files=(b'PK\x03\x04Excel',people))[0],400)
        self.assertEqual(self.snapshot(),before)

    def test_replacement_hashes_password_and_survives_restart(self):
        self.admin()
        self.empty_votes()
        poll = self.polling_client()
        before = self.snapshot()
        status, result = self.upload()
        self.assertEqual(status,200,result)
        self.assertEqual(result['message'],'הנתונים הוכנסו בהצלחה')
        after = self.snapshot()
        self.assertEqual(after[2:4],before[2:4])
        self.assertEqual(len(after[0]),1)
        self.assertEqual(after[0][0][0],'000000009')
        self.assertEqual(poll.request('/api/auth/me')[0],401)
        self.assertEqual(poll.login('1','SyntheticUploadedPassword-123')[0],200)
        self.write_csv() # Obsolete local bootstrap CSV must NOT override uploaded data.
        self.restart()
        self.assertEqual(self.snapshot(),after)
        self.assertEqual(poll.request('/api/auth/me')[0],200)

    def test_time_lock_and_votes_block_replacement(self):
        self.admin()
        self.empty_votes()
        now = datetime.now(timezone.utc)
        self.direct_schedule(now-timedelta(hours=1),now-timedelta(minutes=1))
        before = self.snapshot()
        self.assertEqual(self.upload()[0],409)
        self.assertEqual(self.snapshot(),before)
        self.direct_schedule(now-timedelta(hours=37),now-timedelta(hours=36))
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE People SET Voted=TRUE,VotedAt=UTC_TIMESTAMP(),VotedIn=1 WHERE Id='001234567'")
        self.connection.commit()
        before = self.snapshot()
        self.assertEqual(self.upload()[0],409)
        self.assertEqual(self.snapshot(),before)
        self.empty_votes()
        self.assertEqual(self.upload()[0],200)

    def test_insert_failure_rolls_back_deleted_rows(self):
        self.admin()
        self.empty_votes()
        before = self.snapshot()
        with self.connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER fail_import BEFORE INSERT ON People FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        self.connection.commit()
        try:
            self.assertEqual(self.upload()[0],503)
            self.assertEqual(self.snapshot(),before)
        finally:
            with self.connection.cursor() as cursor: cursor.execute('DROP TRIGGER fail_import')
            self.connection.commit()

    def test_import_status_reports_vote_protection(self):
        self.admin()
        status, data, _ = self.client.request('/api/data')
        self.assertEqual(status,200)
        self.assertTrue(data['hasData'])
        self.assertFalse(data['canImport'])
        self.empty_votes()
        self.assertTrue(self.client.request('/api/data')[1]['canImport'])

    def test_waiting_import_rechecks_start_after_schedule_lock(self):
        self.admin()
        self.empty_votes()
        now = datetime.now(timezone.utc)
        self.direct_schedule(now+timedelta(seconds=2),now+timedelta(hours=1))
        before = self.snapshot()
        blocker = pymysql.connect(**self.options)
        try:
            with blocker.cursor() as cursor:
                cursor.execute('SELECT Id FROM ElectionSettings WHERE Id=1 FOR UPDATE')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.upload)
                deadline = time.monotonic()+1.8
                waiting = False
                while time.monotonic() < deadline:
                    with self.admin_connection.cursor() as cursor:
                        cursor.execute('SELECT COUNT(*) FROM performance_schema.data_lock_waits w JOIN performance_schema.threads t ON t.THREAD_ID=w.BLOCKING_THREAD_ID WHERE t.PROCESSLIST_ID=%s',(blocker.thread_id(),))
                        waiting = cursor.fetchone()[0] > 0
                    if waiting: break
                    time.sleep(.05)
                time.sleep(max(0,2.1-(datetime.now(timezone.utc)-now).total_seconds()))
                blocker.rollback()
                self.assertEqual(future.result()[0],409)
                self.assertTrue(waiting,'Worker must actually wait on the shared gate')
            self.assertEqual(self.snapshot(),before)
        finally:
            blocker.rollback()
            blocker.close()

    def test_two_uploads_serialize_into_complete_datasets(self):
        self.admin()
        self.empty_votes()
        other = previous.votes.election.voters.auth.Client(self.base)
        self.assertEqual(other.login()[0],200)
        first = self.files()
        second = (first[0],first[1].replace(b'000000009',b'000000008'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(self.upload,files=first)
            two = pool.submit(self.upload,client=other,files=second)
            self.assertEqual(one.result()[0],200)
            self.assertEqual(two.result()[0],200)
        rows = self.snapshot()[0]
        self.assertEqual(len(rows),1)
        self.assertIn(rows[0][0],('000000008','000000009'))


if __name__ == '__main__':
    import unittest
    unittest.main()
