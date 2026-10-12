-- A committed upload becomes the authoritative dataset, including station hashes.
CREATE TABLE IF NOT EXISTS DataImportState (
    Id TINYINT PRIMARY KEY,
    ImportedAt DATETIME(6) NOT NULL,
    CONSTRAINT CK_DataImportState_Id CHECK (Id = 1)
);
