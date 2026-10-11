"""Synthetic administrator preview of the UI after password management removal."""
from test_password_csv import PasswordCsvTests

if __name__ == '__main__':
    fixture = PasswordCsvTests('test_manager_password_routes_are_removed')
    try:
        PasswordCsvTests.setUpClass()
        fixture.setUp()
        print('PREVIEW_URL='+PasswordCsvTests.base,flush=True)
        print('Synthetic login: manager@example.test / SyntheticManagerPassword-123',flush=True)
        input('Press Enter to stop and clean up the temporary database.\n')
    finally:
        fixture.doCleanups()
        PasswordCsvTests.doClassCleanups()
