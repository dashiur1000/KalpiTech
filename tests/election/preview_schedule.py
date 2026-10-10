"""Disposable schedule UI preview; all accounts and data are synthetic."""
from test_election import ElectionTests

if __name__ == '__main__':
    fixture = ElectionTests('test_initial_and_future_schedule_with_utc_storage')
    try:
        ElectionTests.setUpClass()
        fixture.setUp()
        print('PREVIEW_URL=' + ElectionTests.base, flush=True)
        print('Synthetic login: manager@example.test / SyntheticManagerPassword-123', flush=True)
        input('Press Enter to stop and remove the temporary database.\n')
    finally:
        fixture.doCleanups()
        ElectionTests.doClassCleanups()
