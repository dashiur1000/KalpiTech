-- Append-only application audit history. No UPDATE or DELETE API is exposed.
CREATE TABLE IF NOT EXISTS AuditLogs (
    Id BIGINT NOT NULL AUTO_INCREMENT,
    OccurredAtUtc DATETIME(6) NOT NULL,
    ActorRole VARCHAR(32) NULL,
    ActorIdentifier VARCHAR(254) NULL,
    Action VARCHAR(64) NOT NULL,
    TargetType VARCHAR(32) NULL,
    TargetIdentifier VARCHAR(128) NULL,
    Result VARCHAR(32) NOT NULL,
    Details VARCHAR(1000) NULL,
    CorrelationId CHAR(36) NULL,
    PRIMARY KEY (Id),
    INDEX IX_AuditLogs_OccurredAtUtc (OccurredAtUtc),
    INDEX IX_AuditLogs_Action (Action),
    INDEX IX_AuditLogs_ActorIdentifier (ActorIdentifier),
    INDEX IX_AuditLogs_Result (Result)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
