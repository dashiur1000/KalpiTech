namespace KalpiTech.Api.Models;

public sealed record ElectionSchedule(DateTime? StartsAt, DateTime? EndsAt)
{
    public DateTime? LoadLockedUntil => StartsAt?.AddHours(36);
    public bool HasStarted(DateTime utcNow) => StartsAt is { } start && utcNow >= start;
    public string State(DateTime utcNow) => !HasStarted(utcNow) ? "Preparation"
        : utcNow < EndsAt ? "Active" : "Finished";
    public bool InCommitteeWindow(DateTime utcNow) => HasStarted(utcNow) && utcNow < LoadLockedUntil;
}
