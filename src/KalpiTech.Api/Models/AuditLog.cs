namespace KalpiTech.Api.Models;

public static class AuditActions
{
    public const string Login = "Login";
    public const string VoterSearch = "VoterSearch";
    public const string VoteConfirmation = "VoteConfirmation";
    public const string DoubleEnvelope = "DoubleEnvelope";
    public const string DataImport = "DataImport";
    public const string ElectionSchedule = "ElectionSchedule";
    public const string StatisticsView = "StatisticsView";
    public const string AuditView = "AuditView";
    public const string EmailSend = "EmailSend";
}

public static class AuditResults
{
    public const string Success = "Success";
    public const string Failed = "Failed";
    public const string Blocked = "Blocked";
    public const string Skipped = "Skipped";
}

public sealed record AuditEvent(
    string Action,
    string Result,
    string? ActorRole = null,
    string? ActorIdentifier = null,
    string? TargetType = null,
    string? TargetIdentifier = null,
    string? Details = null,
    string? CorrelationId = null);

public sealed record AuditLogItem(long Id, DateTime OccurredAtUtc, string? ActorRole,
    string? ActorIdentifier, string Action, string? TargetType, string? TargetIdentifier,
    string Result, string? Details, string? CorrelationId);

public sealed record AuditLogPage(IReadOnlyList<AuditLogItem> Items, int Page, int PageSize,
    long TotalCount, int TotalPages);
