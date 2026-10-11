"""Synthetic active election preview. No production accounts or voters are used."""
from test_votes import VoteTests

if __name__ == '__main__':
    fixture = VoteTests('test_confirm_regular_stores_all_fields_and_cannot_overwrite')
    try:
        VoteTests.setUpClass()
        fixture.setUp()
        fixture.admin()
        fixture.set_station(1)
        fixture.set_station(2)
        fixture.active()
        print('PREVIEW_URL=' + VoteTests.base, flush=True)
        print('Synthetic station 1 or 2 / SyntheticKalpiPassword-456; voter 001234567',flush=True)
        input('Press Enter to stop and clean up the temporary database.\n')
    finally:
        fixture.doCleanups()
        VoteTests.doClassCleanups()
