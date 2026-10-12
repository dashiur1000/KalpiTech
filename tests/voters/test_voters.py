"""Search authorization checks plus the inherited authentication regression suite."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/auth'))
import test_auth as auth


class VoterTests(auth.AuthTests):
    build_directory = '.local/stage05-build'

    def setUp(self):
        super().setUp()
        with self.connection.cursor() as cursor:
            cursor.execute('DELETE FROM People')
            cursor.executemany(
                'INSERT INTO People (Id,KalpiId,FirstName,LastName,EmailAddress) VALUES (%s,%s,%s,%s,%s)',
                [('001234567', 1, 'בדיקה', 'אברג\'יל', 'private@example.test'),
                 ('009876543', 2, 'נגישה', 'בדיקה', None),
                 ('000000001', 1, 'הצביע', 'ראשון', None),
                 ('000000002', 2, 'הצביע', 'שני', None)])
            cursor.execute("UPDATE People SET Voted=TRUE,VotedAt='2026-10-10 12:00:00',VotedIn=2 WHERE Id IN ('000000001','000000002')")
        self.connection.commit()

    def polling_client(self, station=1):
        self.admin()
        self.assertEqual(self.set_station(station)[0], 200)
        client = auth.Client(self.base)
        self.assertEqual(client.login(str(station), auth.KALPI_PASSWORD)[0], 200)
        return client

    def search(self, client, identifier, **extra):
        return client.request('/api/voters/search', {'id': identifier, **extra})

    def test_search_requires_polling_account(self):
        self.client.csrf()
        self.assertEqual(self.search(self.client, '001234567')[0], 401)
        self.admin()
        self.assertEqual(self.search(self.client, '001234567')[0], 403)

    def test_regular_finds_own_voter_with_leading_zeros(self):
        client = self.polling_client()
        status, data, headers = self.search(client, '001234567')
        self.assertEqual(status, 200)
        self.assertEqual(data, {'id': '001234567', 'firstName': 'בדיקה', 'lastName': "אברג'יל", 'kalpiId': 1})
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_unknown_identity_exact_message(self):
        client = self.polling_client()
        status, data, _ = self.search(client, '999999999')
        self.assertEqual(status, 404)
        self.assertEqual(data, {'message': 'שגיאה מספר הזהות אינו במאגר'})

    def test_regular_assignment_precedes_vote_status(self):
        client = self.polling_client()
        for identifier in ('009876543', '000000002'):
            status, data, _ = self.search(client, identifier)
            self.assertEqual(status, 403)
            self.assertEqual(data, {'message': 'הבוחר אינו משתייך לקלפי זה'})

    def test_already_voted_exact_message(self):
        for station in (1, 2):
            client = self.polling_client(station)
            status, data, _ = self.search(client, '000000001')
            self.assertEqual(status, 409)
            self.assertEqual(data, {'message': 'הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה'})

    def test_accessible_finds_voter_from_another_station(self):
        client = self.polling_client(2)
        status, data, _ = self.search(client, '001234567')
        self.assertEqual(status, 200)
        self.assertEqual(data['kalpiId'], 1)

    def test_invalid_identity_inputs(self):
        client = self.polling_client()
        for identifier in (None, '', '12345678', '1234567890', '12345678a', '١٢٣٤٥٦٧٨٩', '001234567\n', "' OR 1=1"):
            with self.subTest(identifier=identifier):
                status, data, _ = self.search(client, identifier)
                self.assertEqual(status, 400)
                self.assertEqual(data, {'message': 'מספר הזהות חייב להכיל תשע ספרות.'})

    def test_client_cannot_override_station_or_role(self):
        client = self.polling_client()
        self.assertEqual(self.search(client, '009876543', kalpiId=2, role='Accessible')[0], 403)

    def test_search_requires_csrf(self):
        client = self.polling_client()
        self.assertEqual(client.request('/api/voters/search', {'id': '001234567'}, csrf=False)[0], 400)

    def test_search_does_not_change_voting_records(self):
        client = self.polling_client(2)
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM People ORDER BY Id')
            before = cursor.fetchall()
        self.connection.commit()
        for identifier in ('001234567', '009876543', '000000001', '999999999'):
            self.search(client, identifier)
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM People ORDER BY Id')
            self.assertEqual(cursor.fetchall(), before)
        self.connection.commit()


if __name__ == '__main__':
    import unittest
    unittest.main()
