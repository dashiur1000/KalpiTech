"""Initialize missing schema/data, then replace this process with the API."""
import os
import sys
from pathlib import Path

ROOT = Path('/workspace')
sys.path.insert(0, str(ROOT / 'tools/data_loader'))
import pymysql
from main import connection_options
from database import bootstrap
from validation import ValidationError


def start():
    try:
        with pymysql.connect(**connection_options()) as connection:
            with connection.cursor() as cursor:
                for script in sorted((ROOT / 'src/KalpiTech.Api/Data/Sql').glob('*.sql')):
                    for statement in script.read_text(encoding='utf-8-sig').split(';'):
                        if statement.strip():
                            cursor.execute(statement)
            connection.commit()
            private_csv = ROOT / '.local/import/kalpi.csv'
            kalpi_csv = private_csv if private_csv.is_file() else ROOT / 'Data/kalpi.csv'
            status, stations, voters = bootstrap(connection, kalpi_csv, ROOT / 'Data/people.csv')
            print(f'Data bootstrap: {status}; stations: {stations}; voters: {voters}.', flush=True)
    except (pymysql.MySQLError, ValidationError, OSError) as error:
        # Error values may contain data or credentials; log only the exception type.
        print(f'Startup failed ({type(error).__name__}); check configuration and CSV files.', file=sys.stderr)
        return 1
    os.execvp('dotnet', ['dotnet', 'KalpiTech.Api.dll'])


if __name__ == '__main__':
    raise SystemExit(start())
