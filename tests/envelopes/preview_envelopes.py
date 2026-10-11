"""Synthetic committee exercise after polling end, within the 36-hour window."""
from datetime import datetime, timedelta, timezone
from test_envelopes import EnvelopeTests

if __name__ == '__main__':
    fixture = EnvelopeTests('test_envelope_window_including_after_polling_end')
    try:
        EnvelopeTests.setUpClass()
        fixture.setUp()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        fixture.direct_schedule(now-timedelta(hours=2),now-timedelta(hours=1))
        print('PREVIEW_URL='+EnvelopeTests.base,flush=True)
        print('Synthetic admin: manager@example.test / SyntheticManagerPassword-123',flush=True)
        print('Synthetic voter: 001234567; committee location: 0000; assigned station: 1.',flush=True)
        input('Press Enter to stop and delete the temporary database.\n')
        row = fixture.row()
        print('PREVIEW_RESULT='+str((row[0],row[1],row[2] is not None,row[3])),flush=True)
    finally:
        fixture.doCleanups()
        EnvelopeTests.doClassCleanups()
