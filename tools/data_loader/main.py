"""Local CLI used by run-api.ps1 before starting ASP.NET Core."""

import argparse
import os
import sys
from pathlib import Path

import pymysql

from database import bootstrap
from validation import ValidationError, validate_files

ROOT = Path(__file__).resolve().parents[2]


def connection_options() -> dict:
    # Process variables take precedence; only explicitly supported settings are read.
    settings = {"MYSQL_PORT": "3307", "MYSQL_DATABASE": "VotesDb", "MYSQL_USER": "kalpitech"}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key in {"MYSQL_PASSWORD", "MYSQL_PORT"}:
                    settings[key] = value.strip()
    for key in ("MYSQL_PASSWORD", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER"):
        if key in os.environ:
            settings[key] = os.environ[key]
    if not settings.get("MYSQL_PASSWORD"):
        raise ValidationError("חסרה הגדרת MYSQL_PASSWORD בקובץ .env.")
    try:
        port = int(settings["MYSQL_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError as error:
        raise ValidationError("MYSQL_PORT חייב להיות מספר בין 1 ל-65535.") from error
    return dict(host="127.0.0.1", port=port, user=settings["MYSQL_USER"],
                password=settings["MYSQL_PASSWORD"], database=settings["MYSQL_DATABASE"],
                charset="utf8mb4", autocommit=False, connect_timeout=5,
                read_timeout=30, write_timeout=30, init_command="SET time_zone = '+00:00'")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CSV or bootstrap an empty VotesDb.")
    parser.add_argument("--validate", action="store_true", help="Validate only; never connect to MySQL.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "Data")
    args = parser.parse_args()
    try:
        kalpi_path = args.data_dir / "kalpi.csv"
        people_path = args.data_dir / "people.csv"
        if args.validate:
            dataset = validate_files(kalpi_path, people_path)
            print(f"הקבצים תקינים: {len(dataset.kalpi)} קלפיות, {len(dataset.people)} בוחרים.")
        else:
            with pymysql.connect(**connection_options()) as connection:
                status, kalpi_count, people_count = bootstrap(connection, kalpi_path, people_path)
            if status == "loaded":
                print("הנתונים הוכנסו בהצלחה")
            else:
                print("המאגר הקיים נשמר; לא בוצעה טעינה מחדש.")
            print(f"קלפיות: {kalpi_count}; בוחרים: {people_count}.")
        return 0
    except ValidationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except pymysql.MySQLError as error:
        # Never log credentials, row values, or provider exception text.
        print(f"הטעינה נכשלה ללא אישור הצלחה. שגיאת מסד מסוג {type(error).__name__}.", file=sys.stderr)
        return 1
    except OSError:
        print("לא ניתן לקרוא את הגדרות הטעינה.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
