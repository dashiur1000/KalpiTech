"""Atomic vote integration checks on a disposable database, plus prior-stage regressions."""
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/election'))
import test_election as election


class VoteTests(election.ElectionTests):
    build_directory = '.local/stage07-build'

    def active(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.direct_schedule(now-timedelta(hours=1),now+timedelta(hours=1))

    def confirm(self, client, identifier='001234567', **extra):
        return client.request('/api/voters/confirm', {'id':identifier, **extra})

    def row(self, identifier='001234567'):
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT KalpiId,Voted,VotedAt,VotedIn FROM People WHERE Id=%s',(identifier,))
            row = cursor.fetchone()
        self.connection.commit()
        return row

    def test_confirm_regular_stores_all_fields_and_cannot_overwrite(self):
        client = self.polling_client()
        self.active()
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        status, data, _ = self.confirm(client, votedIn=2, votedAt='1999-01-01T00:00:00Z', kalpiId=2, role='Accessible')
        self.assertEqual(status,200)
        self.assertEqual(data['message'],'ההצבעה נקלטה בהצלחה!')
        assigned, voted, at, place = self.row()
        self.assertEqual((assigned,voted,place),(1,1,1))
        self.assertTrue(before <= at <= datetime.now(timezone.utc).replace(tzinfo=None))
        self.assertEqual(datetime.fromisoformat(data['votedAt']).replace(tzinfo=None),at)
        saved = self.row()
        self.assertEqual(self.confirm(client)[0],409)
        self.assertEqual(self.row(),saved)

    def test_confirm_accessible_preserves_assignment_and_uses_actual_station(self):
        client = self.polling_client(2)
        self.active()
        self.assertEqual(self.confirm(client)[0],200)
        assigned,voted,at,place = self.row()
        self.assertEqual((assigned,voted,place),(1,1,2))
        self.assertIsNotNone(at)

    def test_confirm_denied_outside_activity_without_mutation(self):
        client = self.polling_client()
        before = self.row()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for schedule in [(None,None),(now+timedelta(hours=1),now+timedelta(hours=2)),
                         (now-timedelta(hours=2),now-timedelta(hours=1))]:
            self.direct_schedule(*schedule)
            status,data,_ = self.confirm(client)
            self.assertEqual(status,409)
            self.assertEqual(data['message'],'אישור הצבעה אפשרי בזמן פעילות הבחירות בלבד.')
            self.assertEqual(self.row(),before)

    def test_confirm_requires_station_authentication_and_csrf(self):
        self.client.csrf()
        self.active()
        self.assertEqual(self.confirm(self.client)[0],401)
        self.admin()
        self.assertEqual(self.confirm(self.client)[0],403)
        client = self.polling_client()
        self.assertEqual(client.request('/api/voters/confirm',{'id':'001234567'},csrf=False)[0],400)
        self.assertEqual(self.row()[1:],(0,None,None))

    def test_confirm_invalid_missing_wrong_assignment_and_duplicate(self):
        client = self.polling_client()
        self.active()
        before = self.row()
        for identifier in (None,'','12345678','1234567890','١٢٣٤٥٦٧٨٩',"' OR 1=1"):
            self.assertEqual(self.confirm(client,identifier)[0],400)
        self.assertEqual(self.confirm(client,'999999999')[0],404)
        self.assertEqual(self.confirm(client,'009876543')[0],403)
        status,data,_ = self.confirm(client,'000000001')
        self.assertEqual(status,409)
        self.assertEqual(data['message'],'שגיאה! הבוחר כבר הצביע ככל הנראה במקום אחר')
        self.assertEqual(self.row(),before)

    def test_assignment_and_password_are_rechecked_after_search(self):
        client = self.polling_client()
        self.active()
        self.assertEqual(self.search(client,'001234567')[0],200)
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE People SET KalpiId=2 WHERE Id='001234567'")
        self.connection.commit()
        self.assertEqual(self.confirm(client)[0],403)
        self.assertEqual(self.set_station(password='ReplacementPassword-789')[0],200)
        self.assertEqual(self.confirm(client)[0],401)
        self.assertEqual(self.row()[1:],(0,None,None))

    def test_parallel_confirmations_have_one_winner(self):
        # Separate authenticated clients; a barrier sends both station types concurrently.
        self.polling_client(1)
        self.polling_client(2)
        clients = []
        for index in range(8):
            client = election.voters.auth.Client(self.base)
            self.assertEqual(client.login(str(1 if index % 2 == 0 else 2), election.voters.auth.KALPI_PASSWORD)[0],200)
            clients.append(client)
        self.active()
        barrier = threading.Barrier(len(clients))
        def send(client):
            barrier.wait(timeout=10)
            return self.confirm(client)
        with ThreadPoolExecutor(max_workers=len(clients)) as pool:
            results = list(pool.map(send,clients))
        self.assertEqual(sum(result[0] == 200 for result in results),1)
        self.assertEqual(sum(result[0] == 409 for result in results),7)
        winner = next(result[1] for result in results if result[0] == 200)
        self.assertEqual(self.row()[3],winner['votedIn'])
        self.assertEqual(self.row()[1],1)

    def test_database_error_rolls_back_and_never_reports_success(self):
        client = self.polling_client()
        self.active()
        before = self.row()
        with self.connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER RejectSyntheticVote BEFORE UPDATE ON People FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        self.connection.commit()
        try:
            status,data,_ = self.confirm(client)
            self.assertEqual(status,503)
            self.assertEqual(data,{'message':'השרת אינו זמין'})
            self.assertEqual(self.row(),before)
        finally:
            with self.connection.cursor() as cursor: cursor.execute('DROP TRIGGER RejectSyntheticVote')
            self.connection.commit()

    def test_time_is_checked_after_waiting_for_voter_lock(self):
        client = self.polling_client()
        blocker = pymysql.connect(**self.options)
        try:
            with blocker.cursor() as cursor:
                cursor.execute("SELECT Id FROM People WHERE Id='001234567' FOR UPDATE")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            self.direct_schedule(now-timedelta(hours=1),now+timedelta(seconds=2))
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.confirm,client)
                # Prove the API is waiting for the lock before crossing the end time.
                waiting = False
                for _ in range(15):
                    with self.connection.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) FROM performance_schema.data_lock_waits AS w JOIN performance_schema.threads AS t ON t.THREAD_ID=w.BLOCKING_THREAD_ID WHERE t.PROCESSLIST_ID=%s", (blocker.thread_id(),))
                        waiting = cursor.fetchone()[0] > 0
                    self.connection.commit()
                    if waiting: break
                    time.sleep(.05)
                self.assertTrue(waiting,'API did not reach the voter-row lock')
                time.sleep(2.1)
                blocker.rollback()
                self.assertEqual(pending.result(timeout=10)[0],409)
            self.assertEqual(self.row()[1:],(0,None,None))
        finally:
            blocker.rollback()
            blocker.close()

    def test_vote_survives_restart_and_search_detects_it(self):
        client = self.polling_client()
        self.active()
        self.assertEqual(self.confirm(client)[0],200)
        before = self.row()
        self.stop_process()
        self.start_process()
        status,data,_ = self.search(client,'001234567')
        self.assertEqual(status,409)
        self.assertEqual(data['message'],'הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה')
        self.assertEqual(self.row(),before)
