"""Disposable manual upload exercise; never connects to the active database."""
from pathlib import Path
from test_import import ImportTests

if __name__ == '__main__':
    fixture = ImportTests('test_replacement_hashes_password_and_survives_restart')
    try:
        ImportTests.setUpClass()
        fixture.setUp()
        fixture.empty_votes()
        preview_directory = Path(ImportTests.temp.name)
        for name, content in zip(('upload-kalpi.csv','upload-people.csv'),fixture.files()):
            (preview_directory/name).write_bytes(content)
        print('PREVIEW_URL='+ImportTests.base,flush=True)
        print('PREVIEW_FILES='+str(preview_directory),flush=True)
        print('Synthetic login: manager@example.test / SyntheticManagerPassword-123',flush=True)
        input('Press Enter to stop the preview and remove its temporary database.\n')
    finally:
        fixture.doCleanups()
        ImportTests.doClassCleanups()
