"""CSV password import and removed management routes, plus voting regressions."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'tests/votes'))
import test_votes as votes


class PasswordCsvTests(votes.VoteTests):
    build_directory = '.local/password-csv-build'

    def setUp(self):
        self.csv_path = Path(self.env['KalpiPasswords__Path'])
        self.csv_path.unlink(missing_ok=True)
        super().setUp()
        self.addCleanup(lambda: self.csv_path.unlink(missing_ok=True))

    def write_csv(self, rows=None):
        rows = rows or [(1,'ImportedStationPassword-111'),(2,'ImportedStationPassword-222'),(3,'ImportedStationPassword-333')]
        with self.csv_path.open('w',encoding='utf-8-sig',newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['KalpiId','City','Place','Address','KalpiType','PasswordHash'])
            for station,password in rows:
                writer.writerow([station,'עיר','מקום, בדיקה','כתובת','Accessible' if station==2 else 'Regular',password])

    def hashes(self):
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT KalpiId,PasswordHash FROM Kalpi ORDER BY KalpiId')
            result = cursor.fetchall()
        self.connection.commit()
        return result

    def restart(self):
        self.stop_process()
        self.start_process()

    def test_csv_import_updates_hashes_and_invalidates_changed_station_cookie(self):
        client = self.polling_client()
        self.write_csv()
        self.restart()
        self.assertEqual(client.request('/api/auth/me')[0],401)
        self.assertEqual(client.login('1','ImportedStationPassword-111')[0],200)
        self.assertEqual(client.login('2','ImportedStationPassword-222')[0],200)
        self.assertEqual(client.login('3','ImportedStationPassword-333')[0],200)
        self.assertTrue(all(password_hash and password_hash.startswith('AQ') for _,password_hash in self.hashes()))

    def test_same_csv_preserves_hash_and_cookie_after_restart(self):
        self.write_csv()
        self.restart()
        client = votes.election.voters.auth.Client(self.base)
        self.assertEqual(client.login('1','ImportedStationPassword-111')[0],200)
        before = self.hashes()
        self.restart()
        self.assertEqual(self.hashes(),before)
        self.assertEqual(client.request('/api/auth/me')[0],200)

    def test_invalid_csv_keeps_all_previous_hashes(self):
        self.polling_client()
        before = self.hashes()
        for rows in [[(1,'ValidSyntheticPassword-111')],
                     [(1,'ValidSyntheticPassword-111'),(1,'ValidSyntheticPassword-222'),(3,'ValidSyntheticPassword-333')],
                     [(1,'ValidSyntheticPassword-111'),(2,'short'),(3,'ValidSyntheticPassword-333')],
                     [(1,'ValidSyntheticPassword-111'),(2,'ValidSyntheticPassword-222'),(99,'ValidSyntheticPassword-333')]]:
            self.write_csv(rows)
            self.stop_process()
            try:
                with self.assertRaises(RuntimeError): self.start_process()
                self.assertEqual(self.hashes(),before)
            finally:
                if self.process.poll() is None: self.stop_process()
                self.csv_path.unlink(missing_ok=True)
                self.start_process()

    def test_quoted_password_and_malformed_csv_do_not_leak_secrets(self):
        password = 'Synthetic,"Password-עברית-123'
        self.write_csv([(1,password),(2,'ImportedStationPassword-222'),(3,'ImportedStationPassword-333')])
        self.restart()
        client = votes.election.voters.auth.Client(self.base)
        self.assertEqual(client.login('1',password)[0],200)
        before = self.hashes()
        leaked_marker = 'SecretMustNotAppear-123'
        self.csv_path.write_text('KalpiId,City,Place,Address,KalpiType,PasswordHash\n1,a,b,c,Regular,"'+leaked_marker,encoding='utf-8')

        self.stop_process()
        try:
            with self.assertRaises(RuntimeError): self.start_process()
            self.log.flush()
            log_bytes = Path(self.log.name).read_bytes()
            self.assertNotIn(leaked_marker.encode('ascii'),log_bytes)
            self.assertNotIn(password.encode('utf-8'),log_bytes)
            self.assertNotIn(password.encode('cp1255'),log_bytes)
            self.assertEqual(self.hashes(),before)
        finally:
            if self.process.poll() is None: self.stop_process()
            self.csv_path.unlink(missing_ok=True)
            self.start_process()
