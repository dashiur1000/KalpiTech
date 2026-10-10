-- Initial schema only. Re-running creates missing tables without deleting data.
-- Future schema changes must use a new numbered script, not edits to this file.
SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS Kalpi (
    KalpiId INTEGER NOT NULL,
    KalpiType VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    City VARCHAR(100) NOT NULL,
    Place VARCHAR(255) NOT NULL,
    Address VARCHAR(255) NOT NULL,
    -- No password until the manager assigns one. NULL must never permit login.
    PasswordHash VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NULL,
    PRIMARY KEY (KalpiId),
    CONSTRAINT CK_Kalpi_Type CHECK (KalpiType IN ('Regular', 'Accessible'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS People (
    Id VARCHAR(9) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    KalpiId INTEGER NOT NULL,
    FirstName VARCHAR(100) NOT NULL,
    LastName VARCHAR(100) NOT NULL,
    Voted BOOLEAN NOT NULL DEFAULT FALSE,
    EmailAddress VARCHAR(254) NULL DEFAULT NULL,
    VotedAt DATETIME(6) NULL DEFAULT NULL COMMENT 'UTC: time of registration',
    VotedIn INTEGER NULL DEFAULT NULL,
    PRIMARY KEY (Id),
    INDEX IX_People_KalpiId (KalpiId),
    INDEX IX_People_VotedIn (VotedIn),
    CONSTRAINT FK_People_AssignedKalpi FOREIGN KEY (KalpiId)
        REFERENCES Kalpi (KalpiId) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT FK_People_ActualKalpi FOREIGN KEY (VotedIn)
        REFERENCES Kalpi (KalpiId) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT CK_People_Id CHECK (REGEXP_LIKE(Id, '^[0-9]{9}$', 'c')),
    CONSTRAINT CK_People_Vote CHECK (
        (Voted = FALSE AND VotedAt IS NULL AND VotedIn IS NULL)
        OR (Voted = TRUE AND VotedAt IS NOT NULL AND VotedIn IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- One election schedule. The current state will be derived from these UTC times.
CREATE TABLE IF NOT EXISTS ElectionSettings (
    Id INTEGER NOT NULL,
    StartsAt DATETIME(6) NULL DEFAULT NULL COMMENT 'UTC',
    EndsAt DATETIME(6) NULL DEFAULT NULL COMMENT 'UTC',
    -- Persisted calculation: always 36 hours after StartsAt, never an independent input.
    LoadLockedUntil DATETIME(6) GENERATED ALWAYS AS
        (DATE_ADD(StartsAt, INTERVAL 36 HOUR)) STORED,
    PRIMARY KEY (Id),
    CONSTRAINT CK_ElectionSettings_Singleton CHECK (Id = 1),
    CONSTRAINT CK_ElectionSettings_Times CHECK (
        (StartsAt IS NULL AND EndsAt IS NULL)
        OR (StartsAt IS NOT NULL AND EndsAt IS NOT NULL AND EndsAt > StartsAt)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Preserve the schedule if it already exists.
INSERT INTO ElectionSettings (Id)
SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM ElectionSettings WHERE Id = 1);
