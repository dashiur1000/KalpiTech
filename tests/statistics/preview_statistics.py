"""Disposable statistics preview with cross-city votes and an empty city."""
from datetime import datetime, timedelta, timezone
from test_statistics import StatisticsTests

if __name__ == '__main__':
    fixture = StatisticsTests('test_statistics_counts_assigned_city_even_when_actual_station_differs')
    try:
        StatisticsTests.setUpClass()
        fixture.setUp()
        fixture.cities_fixture()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        fixture.direct_schedule(now-timedelta(hours=2),now-timedelta(hours=1))
        print('PREVIEW_URL='+StatisticsTests.base,flush=True)
        print('Synthetic admin: manager@example.test / SyntheticManagerPassword-123',flush=True)
        print('Initial participation: 2 of 4 = 50%; each populated city: 1 of 2.',flush=True)
        input('Press Enter to add a synthetic committee vote and check automatic refresh.\n')
        fixture.admin()
        assert fixture.envelope_confirm()[0]==200
        print('Synthetic committee vote committed at 0000: overall 75%, Beit Shemesh 100%, Bnei Brak 50%.',flush=True)
        input('Press Enter again to stop and delete the disposable database.\n')
    finally:
        fixture.doCleanups()
        StatisticsTests.doClassCleanups()
