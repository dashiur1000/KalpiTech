"""Schedule integration checks, with voter/auth regression checks on a disposable database."""
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/voters'))
import test_voters as voters


class ElectionTests(voters.VoterTests):
    build_directory = '.local/stage06-build'

    def setUp(self):
        super().setUp()
        with self.connection.cursor() as cursor:
            cursor.execute('UPDATE ElectionSettings SET StartsAt=NULL,EndsAt=NULL WHERE Id=1')
        self.connection.commit()

    def save(self, start=None, end=None, csrf=True):
        start = start or datetime.now(timezone.utc) + timedelta(days=2)
        end = end or start + timedelta(hours=12)
        local = ZoneInfo('Asia/Jerusalem')
        return self.client.request('/api/election/schedule', {
            'startsAt': start.astimezone(local).strftime('%Y-%m-%dT%H:%M'),
            'endsAt': end.astimezone(local).strftime('%Y-%m-%dT%H:%M')}, csrf=csrf)

    def state(self):
        status, data, _ = self.client.request('/api/election')
        self.assertEqual(status, 200)
        return data

    def direct_schedule(self, start, end):
        # Only the synthetic database is changed to reach time states without waiting.
        with self.connection.cursor() as cursor:
            cursor.execute('UPDATE ElectionSettings SET StartsAt=%s,EndsAt=%s WHERE Id=1', (start, end))
        self.connection.commit()

    def test_schedule_access_and_csrf(self):
        self.client.csrf()
        self.assertEqual(self.client.request('/api/election')[0], 401)
        self.assertEqual(self.save()[0], 401)
        self.admin()
        self.assertEqual(self.save(csrf=False)[0], 400)
        for station in (1, 2):
            client = self.polling_client(station)
            self.assertEqual(client.request('/api/election')[0], 200)
            self.assertEqual(client.request('/api/election/schedule', {'startsAt':'2027-01-01T12:00','endsAt':'2027-01-01T13:00'})[0], 403)

    def test_initial_and_future_schedule_with_utc_storage(self):
        self.admin()
        self.assertEqual(self.state()['state'], 'Preparation')
        start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(days=2)
        self.assertEqual(self.save(start)[0], 200)
        data = self.state()
        self.assertEqual(data['startsAt'], start.isoformat().replace('+00:00','Z'))
        self.assertEqual(data['loadLockedUntil'], (start+timedelta(hours=36)).isoformat().replace('+00:00','Z'))
        self.assertTrue(data['canEdit'])
        self.assertFalse(data['loadLocked'])
        self.assertFalse(data['doubleEnvelopesAllowed'])
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT StartsAt,LoadLockedUntil FROM ElectionSettings WHERE Id=1')
            stored, locked = cursor.fetchone()
        self.connection.commit()
        self.assertEqual(stored, start.replace(tzinfo=None))
        self.assertEqual(locked, stored+timedelta(hours=36))
        self.assertEqual(self.save(start+timedelta(days=1))[0], 200)

    def test_invalid_dates_and_order_do_not_change_schedule(self):
        self.admin()
        self.assertEqual(self.save()[0], 200)
        before = self.state()['startsAt']
        for start, end in [(None,None), ('bad','bad'), ('2026-03-27T02:30','2026-03-27T05:00'),
                           ('2026-10-25T01:30','2026-10-25T05:00'), ('2027-01-01T12:00Z','2027-01-01T13:00Z')]:
            self.assertEqual(self.client.request('/api/election/schedule', {'startsAt':start,'endsAt':end})[0],400)
        now = datetime.now(timezone.utc)
        self.assertEqual(self.save(now+timedelta(days=2), now+timedelta(days=1))[0],400)
        self.assertEqual(self.save(now-timedelta(days=1), now+timedelta(days=1))[0],409)
        self.assertEqual(self.state()['startsAt'],before)

    def test_states_windows_and_edit_lock(self):
        self.admin()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for age, duration, state, window in [(1,12,'Active',True),(13,12,'Finished',True),(37,12,'Finished',False),(37,48,'Active',False)]:
            start = now-timedelta(hours=age)
            self.direct_schedule(start,start+timedelta(hours=duration))
            data = self.state()
            self.assertEqual(data['state'],state)
            self.assertEqual(data['loadLocked'],window)
            self.assertEqual(data['doubleEnvelopesAllowed'],window)
            self.assertFalse(data['canEdit'])
            self.assertEqual(self.save()[0],409)
            self.assertEqual(self.state()['startsAt'],data['startsAt'])

    def test_schedule_survives_api_restart(self):
        self.admin()
        self.assertEqual(self.save()[0],200)
        before = self.state()
        self.stop_process()
        self.start_process()
        after = self.state()
        for field in ('startsAt','endsAt','loadLockedUntil','state','canEdit'):
            self.assertEqual(before[field],after[field])
