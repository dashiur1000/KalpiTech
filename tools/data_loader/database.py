"""Bootstrap only: never replace existing records."""

from datetime import datetime, timezone
from pathlib import Path

from validation import ValidationError, validate_files


def bootstrap(connection, kalpi_path: Path, people_path: Path) -> tuple[str, int, int]:
    connection.begin()
    try:
        with connection.cursor() as cursor:
            # Shared gate for future election start/import/voting operations.
            # Two simultaneous bootstraps serialize on this persisted singleton.
            cursor.execute("SELECT StartsAt FROM ElectionSettings WHERE Id=1 FOR UPDATE")
            schedule = cursor.fetchone()
            if schedule is None:
                raise ValidationError("חסרה רשומת הגדרות הבחירות. הרץ את הקמת הסכמה.")
            cursor.execute("SELECT COUNT(*) FROM Kalpi")
            kalpi_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM People")
            people_count = cursor.fetchone()[0]
            if kalpi_count and people_count:
                # Do not even read the files when using an existing database.
                connection.rollback()
                return "existing", kalpi_count, people_count
            if kalpi_count or people_count:
                raise ValidationError("המאגר מכיל נתונים חלקיים; הטעינה נעצרה ללא שינוי. נדרשת בדיקה לפני המשך.")
            if schedule[0] is not None and schedule[0] <= datetime.now(timezone.utc).replace(tzinfo=None):
                raise ValidationError("לא ניתן לבצע טעינה ראשונית לאחר מועד תחילת הבחירות.")

            dataset = validate_files(kalpi_path, people_path)
            cursor.executemany(
                "INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address) VALUES (%s,%s,%s,%s,%s)",
                dataset.kalpi,
            )
            # Parameters protect names containing apostrophes and avoid SQL injection.
            # Omitted vote fields use the database defaults (FALSE/NULL/NULL).
            for offset in range(0, len(dataset.people), 1000):
                cursor.executemany(
                    "INSERT INTO People (Id,KalpiId,FirstName,LastName,EmailAddress) VALUES (%s,%s,%s,%s,%s)",
                    dataset.people[offset:offset + 1000],
                )
        connection.commit()
        return "loaded", len(dataset.kalpi), len(dataset.people)
    except BaseException:
        connection.rollback()
        raise
