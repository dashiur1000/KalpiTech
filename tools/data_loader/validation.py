"""Validate both CSV files completely before any database writes."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Dataset:
    kalpi: list[tuple]
    people: list[tuple]


KALPI_COLUMNS = {"KalpiId", "City", "Place", "Address", "KalpiType", "PasswordHash"}
PEOPLE_COLUMNS = {"Id", "KalpiId", "FirstName", "LastName", "Voted", "EmailAddress", "VotedAt", "VotedIn"}


def read_rows(path: Path, columns: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True)
            header = reader.fieldnames or []
            if len(header) != len(columns) or set(header) != columns:
                raise ValidationError(f"{path.name}: מבנה העמודות אינו תקין.")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValidationError(f"{path.name}, שורה {reader.line_num}: מספר השדות אינו תקין.")
                rows.append({key: value.strip() for key, value in row.items()})
            if not rows:
                raise ValidationError(f"{path.name}: הקובץ אינו מכיל נתונים.")
            return rows
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValidationError(f"{path.name}: לא ניתן לקרוא קובץ CSV תקין בקידוד UTF-8.") from error


def text(value: str, field: str, limit: int, location: str, required: bool = True) -> str | None:
    if required and not value:
        raise ValidationError(f"{location}: השדה {field} הוא שדה חובה.")
    if len(value) > limit or "\x00" in value:
        raise ValidationError(f"{location}: השדה {field} אינו תקין או ארוך מדי.")
    return value or None


def station_id(value: str, field: str, location: str) -> int:
    if not re.fullmatch(r"[0-9]{1,10}", value) or not 1 <= int(value) <= 2_147_483_647:
        raise ValidationError(f"{location}: השדה {field} חייב להיות מזהה קלפי חיובי בטווח INTEGER.")
    return int(value)


def validate_files(kalpi_path: Path, people_path: Path) -> Dataset:
    kalpi_rows = read_rows(kalpi_path, KALPI_COLUMNS)
    people_rows = read_rows(people_path, PEOPLE_COLUMNS)
    station_ids = set()
    kalpi = []
    for number, row in enumerate(kalpi_rows, start=2):
        location = f"{kalpi_path.name}, רשומה {number}"
        identifier = station_id(row["KalpiId"], "KalpiId", location)
        if identifier in station_ids:
            raise ValidationError(f"{location}: מזהה קלפי כפול.")
        station_ids.add(identifier)
        if row["KalpiType"] not in {"Regular", "Accessible"}:
            raise ValidationError(f"{location}: סוג הקלפי אינו תקין.")
        # CSV passwords are ignored. The manager will assign real password hashes.
        kalpi.append((identifier, row["KalpiType"],
                      text(row["City"], "City", 100, location),
                      text(row["Place"], "Place", 255, location),
                      text(row["Address"], "Address", 255, location)))

    identities = set()
    people = []
    for number, row in enumerate(people_rows, start=2):
        location = f"{people_path.name}, רשומה {number}"
        identifier = row["Id"]
        if not re.fullmatch(r"[0-9]{9}", identifier):
            raise ValidationError(f"{location}: מספר הזהות חייב להכיל תשע ספרות.")
        if identifier in identities:
            raise ValidationError(f"{location}: מספר זהות כפול.")
        identities.add(identifier)
        assigned = station_id(row["KalpiId"], "KalpiId", location)
        if assigned not in station_ids:
            raise ValidationError(f"{location}: הבוחר משויך לקלפי שאינה בקובץ הקלפיות.")
        # Bootstrap accepts an electoral roll, not historical vote records.
        if row["Voted"].upper() != "FALSE" or row["VotedAt"] or row["VotedIn"]:
            raise ValidationError(f"{location}: טעינה ראשונית דורשת Voted=FALSE וללא זמן או מקום הצבעה.")
        people.append((identifier, assigned,
                       text(row["FirstName"], "FirstName", 100, location),
                       text(row["LastName"], "LastName", 100, location),
                       text(row["EmailAddress"], "EmailAddress", 254, location, required=False)))
    return Dataset(kalpi, people)
