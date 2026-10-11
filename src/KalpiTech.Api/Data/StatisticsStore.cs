using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class StatisticsStore(DatabaseConnectionFactory connections, TimeProvider clock)
{
    public async Task<ParticipationReport> ReadAsync(CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        // One SELECT sees a consistent committed snapshot, including during an import.
        // LEFT JOIN includes cities with stations but no assigned voters.
        // VotedIn is deliberately absent: participation belongs to the assigned city.
        await using var command = new MySqlCommand(
            "SELECT k.City,COUNT(p.Id),SUM(CASE WHEN p.Voted=TRUE THEN 1 ELSE 0 END) " +
            "FROM Kalpi k LEFT JOIN People p ON p.KalpiId=k.KalpiId WHERE k.KalpiId>0 GROUP BY k.City ORDER BY k.City", connection);
        var cities = new List<CityParticipation>();
        long total = 0, voted = 0;
        await using var reader = await command.ExecuteReaderAsync(token);
        while (await reader.ReadAsync(token))
        {
            var counts = new Participation(reader.GetInt64(1), reader.GetInt64(2));
            cities.Add(new(reader.GetString(0), counts));
            total += counts.Total;
            voted += counts.Voted;
        }
        return new(new(total, voted), cities, clock.GetUtcNow().UtcDateTime);
    }
}
