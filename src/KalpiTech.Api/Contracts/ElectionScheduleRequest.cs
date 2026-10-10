namespace KalpiTech.Api.Contracts;

// Local Israel wall-clock values, without an offset, supplied by datetime-local inputs.
public sealed record ElectionScheduleRequest(string? StartsAt, string? EndsAt);
