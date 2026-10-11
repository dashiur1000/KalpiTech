"""Manual browser exercise: isolated database and emulator; no real email."""
from test_email import EmailTests

if __name__ == '__main__':
    fixture = EmailTests('test_email_sent_after_committee_vote_without_station_input')
    try:
        EmailTests.setUpClass()
        fixture.setUp()
        fixture.active()
        fixture.set_station(1)
        print('PREVIEW_URL='+EmailTests.base, flush=True)
        print('Synthetic admin: manager@example.test / SyntheticManagerPassword-123', flush=True)
        print('Synthetic station: 1 / SyntheticKalpiPassword-456', flush=True)
        print('Synthetic voter: 001234567; committee location: 0000.', flush=True)
        input('Press Enter to stop and delete the temporary database.\n')
        row = fixture.row()
        print('PREVIEW_RESULT='+str((row[0], row[1], row[2] is not None, row[3])), flush=True)
        print('SIMULATED_EMAIL_ATTEMPTS='+str(len(fixture.records())), flush=True)
    finally:
        fixture.doCleanups()
        EmailTests.doClassCleanups()
