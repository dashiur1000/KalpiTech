"""Append-only audit integration checks plus the complete earlier regression suite."""
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/email'))
import test_email as previous


class AuditTests(previous.EmailTests):
    build_directory = '.local/audit-build'

    def setUp(self):
        super().setUp()
        with self.connection.cursor() as cursor:
            cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()

    def audit_rows(self, action=None):
        self.connection.commit()
        with self.connection.cursor() as cursor:
            sql = ('SELECT Action,Result,ActorRole,ActorIdentifier,TargetType,TargetIdentifier,Details '
                   'FROM AuditLogs' + (' WHERE Action=%s' if action else '') + ' ORDER BY Id')
            cursor.execute(sql, (action,) if action else None)
            rows = cursor.fetchall()
        self.connection.commit()
        return rows

    def test_successful_and_failed_login_are_audited_without_password(self):
        secret = 'NeverStoreThisPassword-987'
        self.assertEqual(self.client.login(password=secret)[0], 401)
        self.assertEqual(self.client.login()[0], 200)
        rows = self.audit_rows('Login')
        self.assertEqual([row[1] for row in rows], ['Failed', 'Success'])
        self.assertEqual(rows[-1][2:4], ('Admin', 'manager@example.test'))
        serialized = repr(rows)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(self.initial_hash, serialized)

    def test_voter_search_results_are_audited(self):
        poll = self.polling_client(1)
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.search(poll, '001234567')[0], 200)
        self.assertEqual(self.search(poll, '999999999')[0], 404)
        self.assertEqual(self.search(poll, '009876543')[0], 403)
        self.assertEqual(self.search(poll, '000000001')[0], 409)
        rows = self.audit_rows('VoterSearch')
        self.assertEqual([row[1] for row in rows], ['Success', 'Blocked', 'Blocked', 'Blocked'])
        self.assertTrue(all(row[4] == 'Voter' for row in rows))

    def test_vote_and_success_audit_are_committed_together(self):
        poll = self.polling_client(1)
        self.active()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.confirm(poll)[0], 200)
        self.assertEqual(self.row()[1], 1)
        rows = self.audit_rows('VoteConfirmation')
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][1], rows[0][2], rows[0][3], rows[0][5]),
                         ('Success', 'Regular', '1', '001234567'))

    def test_audit_insert_failure_rolls_back_vote(self):
        poll = self.polling_client(1)
        self.active()
        before = self.row()
        with self.connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER RejectAudit BEFORE INSERT ON AuditLogs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        self.connection.commit()
        try:
            self.assertEqual(self.confirm(poll)[0], 503)
            self.assertEqual(self.row(), before)
            self.assertEqual(len(self.audit_rows('VoteConfirmation')), 0)
        finally:
            with self.connection.cursor() as cursor: cursor.execute('DROP TRIGGER RejectAudit')
            self.connection.commit()

    def test_vote_database_failure_is_audited_after_rollback(self):
        poll = self.polling_client(1)
        self.active()
        before = self.row()
        with self.connection.cursor() as cursor:
            cursor.execute('DELETE FROM AuditLogs')
            cursor.execute("CREATE TRIGGER RejectVoteForAudit BEFORE UPDATE ON People FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic vote failure'")
        self.connection.commit()
        try:
            self.assertEqual(self.confirm(poll)[0], 503)
            self.assertEqual(self.row(), before)
            rows = self.audit_rows('VoteConfirmation')
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0][1], rows[0][6]), ('Failed', 'כשל במסד הנתונים או בטרנזקציה'))
        finally:
            with self.connection.cursor() as cursor: cursor.execute('DROP TRIGGER RejectVoteForAudit')
            self.connection.commit()

    def test_blocked_parallel_or_duplicate_vote_has_true_result(self):
        poll = self.polling_client(1)
        self.active()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.confirm(poll)[0], 200)
        self.assertEqual(self.confirm(poll)[0], 409)
        rows = self.audit_rows('VoteConfirmation')
        self.assertEqual([row[1] for row in rows], ['Success', 'Blocked'])

    def test_double_envelope_audit_records_committee_location(self):
        self.admin()
        self.active()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.envelope_confirm()[0], 200)
        self.assertEqual(self.row()[3], 0)
        rows = self.audit_rows('DoubleEnvelope')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 'Success')
        self.assertIn('VotedIn=0', rows[0][6])

    def test_audit_api_is_admin_only_and_masks_voter_identity(self):
        self.assertEqual(self.client.request('/api/audit')[0], 401)
        poll = self.polling_client(1)
        self.assertEqual(poll.request('/api/audit')[0], 403)
        self.active()
        self.assertEqual(self.confirm(poll)[0], 200)
        self.admin()
        status, page, _ = self.client.request('/api/audit?page=1&pageSize=100')
        self.assertEqual(status, 200)
        vote = next(item for item in page['items'] if item['action'] == 'VoteConfirmation')
        self.assertEqual(vote['targetIdentifier'], '*****4567')
        self.assertNotIn('001234567', repr(page))

    def test_audit_pagination_and_filters(self):
        self.admin()
        with self.connection.cursor() as cursor:
            cursor.execute('DELETE FROM AuditLogs')
            for index in range(7):
                cursor.execute("INSERT INTO AuditLogs (OccurredAtUtc,ActorRole,ActorIdentifier,Action,Result,Details) VALUES (UTC_TIMESTAMP(6),'Regular',%s,%s,%s,'synthetic safe detail')",
                               ('1' if index < 5 else '2', 'VoterSearch' if index % 2 == 0 else 'Login',
                                'Success' if index < 4 else 'Blocked'))
        self.connection.commit()
        query = urlencode({'page': 1, 'pageSize': 2, 'action': 'VoterSearch', 'actorIdentifier': '1'})
        status, page, _ = self.client.request('/api/audit?' + query)
        self.assertEqual(status, 200)
        self.assertEqual((page['page'], page['pageSize'], page['totalCount'], page['totalPages']), (1, 2, 3, 2))
        self.assertTrue(all(item['action'] == 'VoterSearch' and item['actorIdentifier'] == '1' for item in page['items']))
        self.assertEqual(self.client.request('/api/audit?pageSize=101')[0], 400)

    def test_email_result_is_audited_without_message_or_address(self):
        poll = self.polling_client(1)
        self.active()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.confirm(poll)[0], 200)
        rows = self.audit_rows('EmailSend')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 'Success')
        self.assertNotIn('private@example.test', repr(rows))
        self.assertNotIn('הצבעתך נקלטה בהצלחה', repr(rows))

    def test_admin_views_and_blocked_import_are_audited(self):
        self.admin()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.client.request('/api/statistics')[0], 200)
        self.assertEqual(self.client.request('/api/audit?pageSize=25')[0], 200)
        self.active()
        self.assertEqual(self.client.request('/api/data')[0], 200)
        rows = self.audit_rows()
        self.assertIn(('StatisticsView', 'Success'), [(row[0], row[1]) for row in rows])
        self.assertIn(('AuditView', 'Success'), [(row[0], row[1]) for row in rows])
        self.assertIn(('DataImport', 'Blocked'), [(row[0], row[1]) for row in rows])

    def test_schedule_success_and_locked_change_are_audited(self):
        self.admin()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM AuditLogs')
        self.connection.commit()
        self.assertEqual(self.save()[0], 200)
        self.active()
        self.assertEqual(self.save()[0], 409)
        rows = self.audit_rows('ElectionSchedule')
        self.assertEqual([row[1] for row in rows], ['Success', 'Blocked'])

    def test_no_api_can_modify_or_delete_audit_rows(self):
        self.admin()
        before = len(self.audit_rows())
        self.assertIn(self.client.request('/api/audit/1', {'details': 'changed'})[0], (404, 405))
        self.assertIn(self.client.request('/api/audit/delete', {})[0], (404, 405))
        self.assertEqual(len(self.audit_rows()), before)


if __name__ == '__main__':
    import unittest
    unittest.main()
