"""Aggregated committee statistics, with all earlier API integration regressions."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'tests/envelopes'))
import test_envelopes as previous


class StatisticsTests(previous.EnvelopeTests):
    build_directory = '.local/dashboard-build'

    def cities_fixture(self):
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE Kalpi SET City=CASE KalpiId WHEN 1 THEN 'בית שמש' WHEN 2 THEN 'בני ברק' ELSE 'עיר ללא בוחרים' END")
        self.connection.commit()

    def statistics(self):
        status, report, headers = self.client.request('/api/statistics')
        self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store')
        return report

    def test_statistics_only_admin_can_read(self):
        self.assertEqual(self.client.request('/api/statistics')[0],401)
        for station in (1,2):
            self.assertEqual(self.polling_client(station).request('/api/statistics')[0],403)
        self.admin()
        self.assertEqual(self.statistics()['summary'],{'total':4,'voted':2,'notVoted':2,'percentage':50,
                                                       'activeStations':1,'doubleEnvelopes':0})

    def test_statistics_counts_assigned_city_even_when_actual_station_differs(self):
        self.admin()
        self.cities_fixture()
        report = self.statistics()
        cities = {row['city']:row['counts'] for row in report['cities']}
        # Voter 000000001 is assigned to station 1, but VotedIn=2.
        self.assertEqual(cities['בית שמש'],{'total':2,'voted':1,'notVoted':1,'percentage':50})
        self.assertEqual(cities['בני ברק'],{'total':2,'voted':1,'notVoted':1,'percentage':50})
        self.assertEqual(cities['עיר ללא בוחרים'],{'total':0,'voted':0,'notVoted':0,'percentage':None})
        self.assertEqual(sum(row['total'] for row in cities.values()),report['summary']['total'])
        self.assertEqual(sum(row['voted'] for row in cities.values()),report['summary']['voted'])

    def test_statistics_has_no_personal_fields_and_is_read_only(self):
        self.admin()
        before = self.snapshot()
        report = self.statistics()
        self.assertEqual(set(report),{'summary','election','hourly','cities','stations','votingLocations',
                                      'updatedAt'})
        self.assertEqual(set(report['cities'][0]),{'city','counts'})
        self.assertEqual(set(report['summary']),{'total','voted','notVoted','percentage','activeStations','doubleEnvelopes'})
        forbidden = ('firstName','lastName','emailAddress','passwordHash','001234567','009876543')
        serialized = str(report)
        self.assertTrue(all(value not in serialized for value in forbidden))
        self.assertEqual(self.snapshot(),before)
        updated = datetime.fromisoformat(report['updatedAt']).replace(tzinfo=None)
        self.assertTrue(abs((datetime.now(timezone.utc).replace(tzinfo=None)-updated).total_seconds())<10)

    def test_statistics_empty_database_and_empty_cities(self):
        self.admin()
        self.cities_fixture()
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM People')
        self.connection.commit()
        report = self.statistics()
        self.assertEqual(report['summary'],{'total':0,'voted':0,'notVoted':0,'percentage':None,
                                            'activeStations':0,'doubleEnvelopes':0})
        self.assertEqual(len(report['cities']),3)
        self.assertTrue(all(row['counts']['percentage'] is None for row in report['cities']))
        with self.connection.cursor() as cursor: cursor.execute('DELETE FROM Kalpi')
        self.connection.commit()
        report = self.statistics()
        self.assertEqual(report['cities'],[])
        self.assertEqual(report['summary']['percentage'],None)

    def test_statistics_rounds_percentage_and_handles_zero_or_all_votes(self):
        self.admin()
        self.empty_votes()
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM People WHERE Id='000000002'")
            cursor.execute("UPDATE People SET Voted=TRUE,VotedAt=UTC_TIMESTAMP(),VotedIn=2 WHERE Id='000000001'")
        self.connection.commit()
        self.assertEqual(self.statistics()['summary']['percentage'],33.33)
        self.assertEqual(self.statistics()['summary']['notVoted'],2)
        with self.connection.cursor() as cursor:
            cursor.execute('UPDATE People SET Voted=TRUE,VotedAt=UTC_TIMESTAMP(),VotedIn=2')
        self.connection.commit()
        self.assertEqual(self.statistics()['summary']['percentage'],100)
        self.empty_votes()
        self.assertEqual(self.statistics()['summary']['percentage'],0)

    def test_statistics_refresh_after_committee_vote(self):
        self.admin()
        self.cities_fixture()
        self.active()
        self.assertEqual(self.statistics()['summary']['voted'],2)
        self.assertEqual(self.envelope_confirm()[0],200)
        report = self.statistics()
        self.assertEqual(report['summary']['voted'],3)
        self.assertEqual(report['summary']['percentage'],75)
        self.assertEqual(report['summary']['doubleEnvelopes'],1)
        self.assertEqual(report['votingLocations'],{'assignedStation':1,'otherStation':1,'doubleEnvelopes':1,
                                                    'total':3})
        cities = {row['city']:row['counts'] for row in report['cities']}
        self.assertNotIn('', cities) # Internal committee location is not a city.
        self.assertEqual(cities['בית שמש']['percentage'],100)
        self.assertEqual(cities['בני ברק']['percentage'],50)

    def test_statistics_available_in_all_election_states(self):
        self.admin()
        expected = self.statistics()['summary']
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for schedule in ((None,None),(now+timedelta(hours=1),now+timedelta(hours=2)),
                         (now-timedelta(hours=1),now+timedelta(hours=1)),
                         (now-timedelta(hours=37),now-timedelta(hours=36))):
            self.direct_schedule(*schedule)
            self.assertEqual(self.statistics()['summary'],expected)

    def test_hourly_and_station_activity_are_aggregated_without_station_zero(self):
        self.admin()
        self.cities_fixture()
        now = datetime.now(timezone.utc).replace(minute=30,second=0,microsecond=0,tzinfo=None)
        self.direct_schedule(now-timedelta(hours=2),now+timedelta(hours=2))
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE People SET VotedAt=%s WHERE Id='000000001'",(now-timedelta(hours=1),))
            cursor.execute("UPDATE People SET VotedAt=%s WHERE Id='000000002'",(now,))
        self.connection.commit()
        report = self.statistics()
        self.assertEqual([row['votes'] for row in report['hourly']], [0,1,1])
        self.assertEqual([row['cumulative'] for row in report['hourly']], [0,1,2])
        stations = {row['kalpiId']:row for row in report['stations']}
        self.assertNotIn(0,stations)
        self.assertEqual(stations[2]['actualVotes'],2)
        self.assertEqual(stations[1]['actualVotes'],0)
        self.assertIsNotNone(stations[2]['lastVoteAt'])



if __name__ == '__main__':
    import unittest
    unittest.main()
