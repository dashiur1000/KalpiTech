import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/data_loader"))
from validation import KALPI_COLUMNS, PEOPLE_COLUMNS, ValidationError, validate_files


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.kalpi = [dict(KalpiId="1", City=" בית שמש ", Place="ספרייה", Address="רחוב 1",
                           KalpiType="Regular", PasswordHash="not-a-real-hash")]
        self.people = [dict(Id="001234567", KalpiId="1", FirstName="יוסף", LastName="אברג'יל",
                            Voted="FALSE", EmailAddress="", VotedAt="", VotedIn="")]

    def write_files(self):
        for name, rows, columns in (("kalpi", self.kalpi, KALPI_COLUMNS), ("people", self.people, PEOPLE_COLUMNS)):
            with (self.path / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=sorted(columns))
                writer.writeheader()
                writer.writerows(rows)

    def validate(self):
        return validate_files(self.path / "kalpi.csv", self.path / "people.csv")

    def test_cleaning_and_preservation(self):
        self.write_files()
        dataset = self.validate()
        self.assertEqual(dataset.kalpi, [(1, "Regular", "בית שמש", "ספרייה", "רחוב 1")])
        self.assertEqual(dataset.people, [("001234567", 1, "יוסף", "אברג'יל", None)])

    def test_duplicate_identities(self):
        self.people.append(dict(self.people[0]))
        self.write_files()
        with self.assertRaises(ValidationError): self.validate()

    def test_duplicate_station_normalized_as_integer(self):
        duplicate = dict(self.kalpi[0], KalpiId="01")
        self.kalpi.append(duplicate)
        self.write_files()
        with self.assertRaises(ValidationError): self.validate()

    def test_invalid_people_fields(self):
        for field, value in (("Id", "12345678"), ("Id", "12345678a"), ("Id", "١٢٣٤٥٦٧٨٩"),
                             ("KalpiId", "2"), ("FirstName", " "), ("LastName", "a" * 101),
                             ("EmailAddress", "a" * 255), ("Voted", "TRUE"), ("Voted", "other"),
                             ("VotedAt", "2026-10-10"), ("VotedIn", "1")):
            with self.subTest(field=field, value=value):
                original = self.people[0][field]
                self.people[0][field] = value
                self.write_files()
                with self.assertRaises(ValidationError): self.validate()
                self.people[0][field] = original

    def test_invalid_station_fields(self):
        for field, value in (("KalpiId", "0"), ("KalpiId", "2147483648"), ("KalpiId", "1.0"),
                             ("KalpiType", "regular"), ("City", ""), ("Place", "a" * 256), ("Address", "")):
            with self.subTest(field=field, value=value):
                original = self.kalpi[0][field]
                self.kalpi[0][field] = value
                self.write_files()
                with self.assertRaises(ValidationError): self.validate()
                self.kalpi[0][field] = original

    def test_bad_headers_and_row_lengths(self):
        self.write_files()
        path = self.path / "people.csv"
        for content in ("Id,Id\n1,2\n", "Id,KalpiId\n1,2\n",
                        ",".join(sorted(PEOPLE_COLUMNS)) + "\n1,2\n",
                        ",".join(sorted(PEOPLE_COLUMNS)) + "\n" + ",".join(["x"] * 9) + "\n"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValidationError): self.validate()

    def test_empty_and_missing_files(self):
        self.write_files()
        self.people.clear()
        self.write_files()
        with self.assertRaises(ValidationError): self.validate()
        (self.path / "people.csv").unlink()
        with self.assertRaises(ValidationError): self.validate()

    def test_invalid_email_is_kept_for_mail_stage(self):
        self.people[0]["EmailAddress"] = "not-an-email"
        self.write_files()
        self.assertEqual(self.validate().people[0][-1], "not-an-email")


if __name__ == "__main__":
    unittest.main()
