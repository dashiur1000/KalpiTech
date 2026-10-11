"""Real API/MySQL, synthetic recipients and a loopback-only Brevo emulator."""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/statistics'))
import test_statistics as previous


class BrevoEmulator(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
            chunks = []
            while True:
                length = int(self.rfile.readline().split(b';', 1)[0].strip(), 16)
                if length == 0:
                    while self.rfile.readline().strip():
                        pass
                    break
                chunks.append(self.rfile.read(length))
                self.rfile.read(2) # CRLF after this chunk.
            raw = b''.join(chunks)
        else:
            raw = self.rfile.read(int(self.headers['Content-Length']))
        body = json.loads(raw)
        # An independent connection sees only committed data, proving mail follows COMMIT.
        committed = self.server.observe_vote()
        with self.server.records_lock:
            self.server.records.append((self.path, self.headers.get('api-key'), body, committed))
            status, delay = self.server.reply_status, self.server.delay
        time.sleep(delay)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        try:
            self.wfile.write(b'{"messageId":"synthetic-message"}')
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass # Timeout scenario: the client already closed the connection.

    def log_message(self, *args):
        pass


class EmailTests(previous.StatisticsTests):
    build_directory = '.local/stage11-build'
    email_enabled = True

    @classmethod
    def setUpClass(cls):
        cls.emulator = ThreadingHTTPServer(('127.0.0.1', 0), BrevoEmulator)
        cls.emulator.records_lock = threading.Lock()
        cls.emulator.records = []
        cls.emulator.reply_status = 201
        cls.emulator.delay = 0
        cls.emulator.observe_vote = cls.observe_committed_vote
        cls.emulator_thread = threading.Thread(target=cls.emulator.serve_forever, daemon=True)
        cls.emulator_thread.start()
        cls.addClassCleanup(cls.close_emulator)
        super().setUpClass()

    @classmethod
    def observe_committed_vote(cls):
        with pymysql.connect(**cls.options) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT Voted FROM People WHERE Id='001234567'")
                row = cursor.fetchone()
                return row is not None and bool(row[0])

    @classmethod
    def close_emulator(cls):
        cls.emulator.shutdown()
        cls.emulator.server_close()
        cls.emulator_thread.join(timeout=5)

    @classmethod
    def start_process(cls):
        cls.env.update(ASPNETCORE_ENVIRONMENT='Testing', Mail__Enabled=str(cls.email_enabled).lower(),
                       Mail__ApiKey='synthetic-api-key', Mail__SenderEmail='sender@example.test',
                       Mail__SenderName='ועדת הבחירות',
                       Mail__TestBaseUrl=f'http://127.0.0.1:{cls.emulator.server_port}/v3/')
        super().start_process()

    def setUp(self):
        super().setUp()
        with self.emulator.records_lock:
            self.emulator.records.clear()
            self.emulator.reply_status = 201
            self.emulator.delay = 0

    def records(self):
        with self.emulator.records_lock:
            return list(self.emulator.records)

    def assert_single_mail(self):
        records = self.records()
        self.assertEqual(len(records), 1)
        path, key, body, committed = records[0]
        self.assertTrue(committed, 'Email was attempted before the vote COMMIT')
        self.assertEqual(path, '/v3/smtp/email')
        self.assertEqual(key, 'synthetic-api-key')
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT FirstName,LastName,EmailAddress FROM People WHERE Id='001234567'")
            first, last, address = cursor.fetchone()
        self.assertEqual(body['sender'], {'email':'sender@example.test','name':'ועדת הבחירות'})
        self.assertEqual(body['to'], [{'email':address,'name':f'{first} {last}'}])
        self.assertEqual(body['subject'], 'וועדת הבחירות המרכזית - אישור הצבעה')
        self.assertEqual(body['textContent'], f'שלום {first} {last}, הצבעתך נקלטה בהצלחה!')
        self.assertEqual(set(body), {'sender','to','subject','textContent'})

    def test_email_sent_once_after_regular_vote(self):
        poll = self.polling_client(1)
        self.active()
        self.assertEqual(self.confirm(poll)[0], 200)
        self.assert_single_mail()
        before = self.row()
        self.assertEqual(self.confirm(poll)[0], 409)
        self.assertEqual(self.row(), before)
        self.assert_single_mail()

    def test_email_sent_after_committee_vote_without_station_input(self):
        self.admin()
        self.active()
        self.assertEqual(self.envelope_confirm()[0], 200)
        self.assertEqual(self.row()[3], 0)
        self.assert_single_mail()
        self.assertEqual(self.envelope_confirm()[0], 409)
        self.assert_single_mail()

    def test_email_missing_or_invalid_address_is_skipped(self):
        poll = self.polling_client(1)
        self.active()
        for address in (None, '', 'invalid', 'Name <private@example.test>', 'private@example.test\n'):
            with self.connection.cursor() as cursor:
                cursor.execute("UPDATE People SET Voted=FALSE,VotedAt=NULL,VotedIn=NULL,EmailAddress=%s WHERE Id='001234567'", (address,))
            self.connection.commit()
            self.assertEqual(self.confirm(poll)[0], 200)
            self.assertEqual(self.row()[1], 1)
            self.assertEqual(self.records(), [])

    def test_email_provider_failure_does_not_rollback_or_retry(self):
        self.emulator.reply_status = 503
        self.admin()
        self.active()
        self.assertEqual(self.envelope_confirm()[0], 200)
        self.assertEqual(self.row()[1], 1)
        self.assert_single_mail()
        self.assertEqual(self.envelope_confirm()[0], 409)
        self.assert_single_mail()

    def test_email_timeout_does_not_rollback_or_retry(self):
        self.emulator.delay = 6
        poll = self.polling_client(1)
        self.active()
        started = time.monotonic()
        self.assertEqual(self.confirm(poll)[0], 200)
        self.assertLess(time.monotonic()-started, 9)
        self.assertEqual(self.row()[1], 1)
        self.assert_single_mail()

    def test_email_is_not_sent_for_unsuccessful_vote(self):
        poll = self.polling_client(1)
        self.assertEqual(self.confirm(poll)[0], 409)
        self.active()
        self.assertEqual(self.confirm(poll, identifier='999999999')[0], 404)
        self.assertEqual(self.confirm(poll, identifier='009876543')[0], 403)
        self.assertEqual(self.confirm(poll, identifier='000000001')[0], 409)
        self.assertEqual(self.records(), [])

    def test_email_parallel_votes_send_only_once(self):
        self.test_parallel_committee_and_polling_confirmations_have_one_winner()
        self.assert_single_mail()

    def test_email_database_rollback_sends_nothing(self):
        self.test_envelope_rollback_on_database_error()
        self.assertEqual(self.records(), [])

    def test_email_disabled_configuration_sends_nothing(self):
        type(self).email_enabled = False
        try:
            self.restart()
            self.admin()
            self.active()
            self.assertEqual(self.envelope_confirm()[0], 200)
            self.assertEqual(self.records(), [])
        finally:
            type(self).email_enabled = True
            self.restart()

    def test_email_logs_do_not_contain_recipient_key_or_body(self):
        self.emulator.reply_status = 503
        self.admin()
        self.active()
        self.assertEqual(self.envelope_confirm()[0], 200)
        self.assert_single_mail()
        self.log.flush()
        log = Path(self.log.name).read_text(encoding='utf-8')
        for private in ('private@example.test', 'synthetic-api-key', 'הצבעתך נקלטה בהצלחה!'):
            self.assertNotIn(private, log)


if __name__ == '__main__':
    import unittest
    unittest.main()
