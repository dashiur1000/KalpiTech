namespace KalpiTech.Api.Models;

public sealed record Participation(long Total, long Voted)
{
    public long NotVoted => Total - Voted;
    public decimal? Percentage => Total == 0 ? null : Math.Round(100m * Voted / Total, 2);
}

public sealed record CityParticipation(string City, Participation Counts);

public sealed record DashboardSummary(long Total, long Voted, long ActiveStations, long DoubleEnvelopes)
{
    public long NotVoted => Total - Voted;
    public decimal? Percentage => Total == 0 ? null : Math.Round(100m * Voted / Total, 2);
}

public sealed record ElectionDashboard(string State, DateTime? StartsAt, DateTime? EndsAt, long? RemainingSeconds);
public sealed record HourlyParticipation(DateTime BucketStart, long Votes, long Cumulative);
public sealed record StationParticipation(int KalpiId, string City, string KalpiType,
    Participation Assigned, long ActualVotes, DateTime? LastVoteAt);

public sealed record VotingLocationBreakdown(long AssignedStation, long OtherStation, long DoubleEnvelopes)
{
    public long Total => AssignedStation + OtherStation + DoubleEnvelopes;
}

public sealed record ParticipationReport(DashboardSummary Summary, ElectionDashboard Election,
    IReadOnlyList<HourlyParticipation> Hourly, IReadOnlyList<CityParticipation> Cities,
    IReadOnlyList<StationParticipation> Stations, VotingLocationBreakdown VotingLocations, DateTime UpdatedAt);
