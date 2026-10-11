"""API-only worker: validate first, then replace everything in one transaction."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymysql
from main import connection_options
from validation import ValidationError, validate_files


def replace(connection, directory):
    dataset = validate_files(directory / 'kalpi.csv', directory / 'people.csv')
    hashes = json.loads((directory / 'hashes.json').read_text(encoding='utf-8'))
    if set(hashes) != {str(row[0]) for row in dataset.kalpi}:
        raise ValidationError('גיבובי הקלפיות אינם תואמים לקובץ.')
    connection.begin()
    try:
        with connection.cursor() as cursor:
            # Same gate as schedule changes and voting. Check time AFTER waiting.
            cursor.execute('SELECT StartsAt FROM ElectionSettings WHERE Id=1 FOR UPDATE')
            settings = cursor.fetchone()
            if settings is None:
                raise ValidationError('חסרה רשומת הגדרות הבחירות.')
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start = settings[0]
            if start is not None and start <= now < start + timedelta(hours=36):
                connection.rollback()
                return {'status': 409, 'message': 'טעינת הנתונים נעולה למשך 36 שעות ממועד תחילת הבחירות.'}
            cursor.execute('SELECT COUNT(*) FROM People WHERE Voted=TRUE')
            if cursor.fetchone()[0]:
                connection.rollback()
                return {'status': 409, 'message': 'לא ניתן להחליף מאגר המכיל רישומי הצבעה.'}
            cursor.execute('DELETE FROM People')
            cursor.execute('DELETE FROM Kalpi WHERE KalpiId>0')
            cursor.executemany('INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address,PasswordHash) VALUES (%s,%s,%s,%s,%s,%s)',
                               [(*row, hashes[str(row[0])]) for row in dataset.kalpi])
            for offset in range(0, len(dataset.people), 1000):
                cursor.executemany('INSERT INTO People (Id,KalpiId,FirstName,LastName,EmailAddress) VALUES (%s,%s,%s,%s,%s)',
                                   dataset.people[offset:offset+1000])
            cursor.execute('INSERT INTO DataImportState (Id,ImportedAt) VALUES (1,%s) ON DUPLICATE KEY UPDATE ImportedAt=VALUES(ImportedAt)', (now,))
        connection.commit()
        return {'status': 200, 'message': 'הנתונים הוכנסו בהצלחה', 'kalpiCount': len(dataset.kalpi), 'peopleCount': len(dataset.people)}
    except BaseException:
        connection.rollback()
        raise


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        with pymysql.connect(**connection_options()) as connection:
            result = replace(connection, Path(sys.argv[1]))
    except ValidationError as error:
        result = {'status': 400, 'message': str(error)}
    except Exception:
        # No traceback/row contents/passwords enter the process output.
        result = {'status': 503, 'message': 'הטעינה לא קיבלה אישור הצלחה. יש לבדוק את המאגר לפני ניסיון נוסף.'}
    print(json.dumps(result, ensure_ascii=False))
