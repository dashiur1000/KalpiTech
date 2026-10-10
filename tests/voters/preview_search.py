"""Disposable UI preview: synthetic data only; press Enter to remove it."""
from test_voters import VoterTests


if __name__ == '__main__':
    fixture = VoterTests('test_regular_finds_own_voter_with_leading_zeros')
    try:
        VoterTests.setUpClass()
        fixture.setUp()
        fixture.admin()
        fixture.set_station(1)
        fixture.set_station(2)
        print('PREVIEW_URL=' + VoterTests.base, flush=True)
        print('Synthetic stations: 1 (Regular), 2 (Accessible). Password: SyntheticKalpiPassword-456', flush=True)
        input('Press Enter to stop the preview and clean up its temporary database.\n')
    finally:
        fixture.doCleanups()
        VoterTests.doClassCleanups()
