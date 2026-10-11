namespace KalpiTech.Api.Models;

public sealed record Participation(long Total, long Voted)
{
    public decimal? Percentage => Total == 0 ? null : Math.Round(100m * Voted / Total, 2);
}
public sealed record CityParticipation(string City, Participation Counts);
public sealed record ParticipationReport(Participation Overall, IReadOnlyList<CityParticipation> Cities, DateTime UpdatedAt);
