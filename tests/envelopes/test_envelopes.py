"""Committee envelope registration with real MySQL and all earlier API regressions."""
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'tests/data_import'))
import test_import as imports
Client = imports.previous.votes.election.voters.auth.Client


class EnvelopeTests(imports.ImportTests):
    build_directory = '.local/stage09-build'

    def envelope_search(self, client=None, identifier='001234567', csrf=True):
        return (client or self.client).request('/api/envelopes/search',{'id':identifier},csrf=csrf)

    def envelope_confirm(self, client=None, identifier='001234567', csrf=True, **extra):
        return (client or self.client).request('/api/envelopes/confirm',{'id':identifier,**extra},csrf=csrf)

    def test_envelope_auth_roles_and_csrf(self):
        self.client.csrf()
        self.active()
        self.assertEqual(self.envelope_search()[0],401)
        self.assertEqual(self.envelope_confirm()[0],401)
        for station in (1,2):
            poll = self.polling_client(station)
            self.assertEqual(self.envelope_search(poll)[0],403)
            self.assertEqual(self.envelope_confirm(poll)[0],403)
        self.admin()
        self.assertEqual(self.envelope_search(csrf=False)[0],400)
        self.assertEqual(self.envelope_confirm(csrf=False)[0],400)
        self.assertEqual(self.row()[1:],(0,None,None))

    def test_envelope_search_any_assignment_is_read_only(self):
        self.admin()
        self.active()
        before = self.snapshot()
        for identifier in ('001234567','009876543'):
            status, data, _ = self.envelope_search(identifier=identifier)
            self.assertEqual(status,200)
            self.assertEqual(set(data),{'id','firstName','lastName','kalpiId'})
        self.assertEqual(self.snapshot(),before)

    def test_envelope_saves_committee_location_and_server_utc_time(self):
        self.admin()
        self.active()
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        status, data, _ = self.envelope_confirm(votedAt='1999-01-01T00:00:00Z',kalpiId=3,role='Regular')
        self.assertEqual(status,200)
        self.assertEqual(data['message'],'ההצבעה נקלטה בהצלחה!')
        assigned, voted, at, place = self.row()
        self.assertEqual((assigned,voted,place),(1,1,0))
        self.assertTrue(before <= at <= datetime.now(timezone.utc).replace(tzinfo=None))
        self.assertEqual(data['votedIn'],0)
        self.assertEqual(data['votedInLabel'],'0000 — ועדת הבחירות')
        self.assertEqual(datetime.fromisoformat(data['votedAt']).replace(tzinfo=None),at)
        saved = self.row()
        self.assertEqual(self.envelope_confirm()[0],409)
        self.assertEqual(self.row(),saved)

    def test_envelope_window_including_after_polling_end(self):
        self.admin()
        before = self.row()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for schedule in ((None,None),(now+timedelta(hours=1),now+timedelta(hours=2)),
                         (now-timedelta(hours=37),now-timedelta(hours=36))):
            self.direct_schedule(*schedule)
            self.assertEqual(self.envelope_search()[0],409)
            self.assertEqual(self.envelope_confirm()[0],409)
            self.assertEqual(self.row(),before)
        self.direct_schedule(now-timedelta(hours=2),now-timedelta(hours=1))
        self.assertEqual(self.envelope_search()[0],200)
        self.assertEqual(self.envelope_confirm()[0],200)

    def test_envelope_invalid_id_unknown_voter_and_duplicate(self):
        self.admin()
        self.active()
        before = self.row()
        for identifier in (None,'','12345678','1234567890','١٢٣٤٥٦٧٨٩',"' OR 1=1"):
            self.assertEqual(self.envelope_search(identifier=identifier)[0],400)
            self.assertEqual(self.envelope_confirm(identifier=identifier)[0],400)
        self.assertEqual(self.envelope_search(identifier='999999999')[0],404)
        self.assertEqual(self.envelope_confirm(identifier='999999999')[0],404)
        status, data, _ = self.envelope_search(identifier='000000001')
        self.assertEqual(status,409)
        self.assertEqual(data['message'],'הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה')
        status, data, _ = self.envelope_confirm(identifier='000000001')
        self.assertEqual(status,409)
        self.assertEqual(data['message'],'שגיאה! הבוחר כבר הצביע ככל הנראה במקום אחר')
        self.assertEqual(self.row(),before)

    def test_client_cannot_override_committee_location(self):
        self.admin()
        self.active()
        self.assertEqual(self.envelope_search()[0],200)
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM Kalpi WHERE KalpiId=3')
        self.connection.commit()
        self.assertEqual(self.envelope_confirm(votedIn=3)[0],200)
        self.assertEqual(self.row()[3],0)

    def test_committee_location_cannot_login_or_be_overwritten_by_csv(self):
        self.admin()
        self.active()
        self.assertEqual(self.envelope_confirm()[0],200)
        client = Client(self.base)
        self.assertEqual(client.login('0000','SyntheticAnyPassword-123')[0],401)
        self.write_csv()
        self.restart()
        self.assertEqual(self.row()[3],0)
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT PasswordHash FROM Kalpi WHERE KalpiId=0')
            self.assertIsNone(cursor.fetchone()[0])

    def test_parallel_committee_and_polling_confirmations_have_one_winner(self):
        self.admin()
        self.set_station(1)
        self.set_station(2)
        clients = []
        for index in range(8):
            client = Client(self.base)
            if index % 2 == 0: self.assertEqual(client.login()[0],200)
            else: self.assertEqual(client.login(str(1 if index % 4 == 1 else 2),imports.previous.votes.election.voters.auth.KALPI_PASSWORD)[0],200)
            clients.append((client,index % 2 == 0))
        self.active()
        barrier = threading.Barrier(len(clients))
        def send(pair):
            client, committee = pair
            barrier.wait(timeout=10)
            return self.envelope_confirm(client) if committee else self.confirm(client)
        with ThreadPoolExecutor(max_workers=len(clients)) as pool: results = list(pool.map(send,clients))
        self.assertEqual(sum(result[0]==200 for result in results),1)
        self.assertEqual(sum(result[0]==409 for result in results),7)
        self.assertEqual(self.row()[3],next(result[1]['votedIn'] for result in results if result[0]==200))

    def test_envelope_rollback_on_database_error(self):
        self.admin()
        self.active()
        before = self.row()
        with self.connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER RejectEnvelope BEFORE UPDATE ON People FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        self.connection.commit()
        try:
            self.assertEqual(self.envelope_confirm()[0],503)
            self.assertEqual(self.row(),before)
            with self.connection.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM Kalpi WHERE KalpiId=0')
                self.assertEqual(cursor.fetchone()[0],0)
            self.connection.commit()
        finally:
            with self.connection.cursor() as cursor: cursor.execute('DROP TRIGGER RejectEnvelope')
            self.connection.commit()

    def test_envelope_time_rechecked_after_waiting_for_voter_lock(self):
        self.admin()
        blocker = pymysql.connect(**self.options)
        try:
            with blocker.cursor() as cursor: cursor.execute("SELECT Id FROM People WHERE Id='001234567' FOR UPDATE")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            self.direct_schedule(now-timedelta(hours=36)+timedelta(seconds=2),now-timedelta(hours=1))
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.envelope_confirm)
                waiting = False
                for _ in range(15):
                    with self.connection.cursor() as cursor:
                        cursor.execute('SELECT COUNT(*) FROM performance_schema.data_lock_waits w JOIN performance_schema.threads t ON t.THREAD_ID=w.BLOCKING_THREAD_ID WHERE t.PROCESSLIST_ID=%s',(blocker.thread_id(),))
                        waiting = cursor.fetchone()[0] > 0
                    self.connection.commit()
                    if waiting: break
                    time.sleep(.05)
                time.sleep(2.1)
                blocker.rollback()
                self.assertTrue(waiting,'Request did not reach the voter lock')
                self.assertEqual(pending.result(timeout=10)[0],409)
            self.assertEqual(self.row()[1:],(0,None,None))
        finally:
            blocker.rollback()
            blocker.close()

    def test_envelope_survives_restart_and_blocks_data_replacement(self):
        self.admin()
        self.active()
        self.assertEqual(self.envelope_confirm()[0],200)
        before = self.row()
        self.restart()
        self.assertEqual(self.row(),before)
        self.assertEqual(self.envelope_search()[0],409)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.direct_schedule(now-timedelta(hours=37),now-timedelta(hours=36))
        self.assertEqual(self.upload()[0],409)
        self.assertEqual(self.row(),before)


if __name__ == '__main__':
    import unittest
    unittest.main()
