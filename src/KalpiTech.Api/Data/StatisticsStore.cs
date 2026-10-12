using System.Data;
using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class StatisticsStore(DatabaseConnectionFactory connections, TimeProvider clock)
{
    public async Task<ParticipationReport> ReadAsync(CancellationToken token)
    {
        var now = clock.GetUtcNow().UtcDateTime;
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead, token);

        var schedule = await ElectionStore.ReadRowAsync(connection, transaction, token);
        var summaryAndLocations = await ReadSummaryAsync(connection, transaction, token);
        var cities = await ReadCitiesAsync(connection, transaction, token);
        var stations = await ReadStationsAsync(connection, transaction, token);
        var hourly = await ReadHourlyAsync(connection, transaction, token);
        await transaction.CommitAsync(token);

        hourly = FillEmptyHours(hourly, schedule, now);
        long cumulative = 0;
        var hourlyWithCumulative = hourly.Select(bucket =>
        {
            cumulative += bucket.Votes;
            return bucket with { Cumulative = cumulative };
        }).ToList();
        var state = schedule.State(now);
        long? remaining = state == "Active" && schedule.EndsAt is { } end
            ? Math.Max(0, (long)(end - now).TotalSeconds) : null;
        return new(summaryAndLocations.Summary,
            new(state, schedule.StartsAt, schedule.EndsAt, remaining), hourlyWithCumulative,
            cities, stations, summaryAndLocations.Locations, now);
    }

    private static async Task<(DashboardSummary Summary, VotingLocationBreakdown Locations)> ReadSummaryAsync(
        MySqlConnection connection, MySqlTransaction transaction, CancellationToken token)
    {
        const string sql = """
            SELECT COUNT(*),
              SUM(CASE WHEN Voted=TRUE THEN 1 ELSE 0 END),
              COUNT(DISTINCT CASE WHEN Voted=TRUE AND VotedIn>0 THEN VotedIn END),
              SUM(CASE WHEN Voted=TRUE AND VotedIn=0 THEN 1 ELSE 0 END),
              SUM(CASE WHEN Voted=TRUE AND VotedIn=KalpiId THEN 1 ELSE 0 END),
              SUM(CASE WHEN Voted=TRUE AND VotedIn>0 AND VotedIn<>KalpiId THEN 1 ELSE 0 END)
            FROM People
            """;
        await using var command = new MySqlCommand(sql, connection, transaction);
        await using var reader = await command.ExecuteReaderAsync(token);
        await reader.ReadAsync(token);
        long Value(int index) => reader.IsDBNull(index) ? 0 : reader.GetInt64(index);
        return (new(Value(0), Value(1), Value(2), Value(3)), new(Value(4), Value(5), Value(3)));
    }

    private static async Task<List<CityParticipation>> ReadCitiesAsync(MySqlConnection connection,
        MySqlTransaction transaction, CancellationToken token)
    {
        const string sql = """
            SELECT k.City,COUNT(p.Id),SUM(CASE WHEN p.Voted=TRUE THEN 1 ELSE 0 END)
            FROM Kalpi k LEFT JOIN People p ON p.KalpiId=k.KalpiId
            WHERE k.KalpiId>0 GROUP BY k.City ORDER BY k.City
            """;
        await using var command = new MySqlCommand(sql, connection, transaction);
        await using var reader = await command.ExecuteReaderAsync(token);
        var rows = new List<CityParticipation>();
        while (await reader.ReadAsync(token))
            rows.Add(new(reader.GetString(0), new(reader.GetInt64(1), reader.GetInt64(2))));
        return rows;
    }

    private static async Task<List<StationParticipation>> ReadStationsAsync(MySqlConnection connection,
        MySqlTransaction transaction, CancellationToken token)
    {
        const string sql = """
            SELECT k.KalpiId,k.City,k.KalpiType,
              COALESCE(a.Total,0),COALESCE(a.Voted,0),COALESCE(v.ActualVotes,0),v.LastVoteAt
            FROM Kalpi k
            LEFT JOIN (SELECT KalpiId,COUNT(*) Total,SUM(CASE WHEN Voted=TRUE THEN 1 ELSE 0 END) Voted
                       FROM People GROUP BY KalpiId) a ON a.KalpiId=k.KalpiId
            LEFT JOIN (SELECT VotedIn,COUNT(*) ActualVotes,MAX(VotedAt) LastVoteAt
                       FROM People WHERE Voted=TRUE AND VotedIn>0 GROUP BY VotedIn) v ON v.VotedIn=k.KalpiId
            WHERE k.KalpiId>0 ORDER BY k.KalpiId
            """;
        await using var command = new MySqlCommand(sql, connection, transaction);
        await using var reader = await command.ExecuteReaderAsync(token);
        var rows = new List<StationParticipation>();
        while (await reader.ReadAsync(token))
            rows.Add(new(reader.GetInt32(0), reader.GetString(1), reader.GetString(2),
                new(reader.GetInt64(3), reader.GetInt64(4)), reader.GetInt64(5),
                reader.IsDBNull(6) ? null : reader.GetDateTime(6)));
        return rows;
    }

    private static async Task<List<HourlyParticipation>> ReadHourlyAsync(MySqlConnection connection,
        MySqlTransaction transaction, CancellationToken token)
    {
        // UTC buckets are converted for display outside MySQL, so MySQL time-zone tables are not required.
        const string sql = """
            SELECT DATE_FORMAT(VotedAt,'%Y-%m-%d %H:00:00'),COUNT(*)
            FROM People WHERE Voted=TRUE
            GROUP BY DATE_FORMAT(VotedAt,'%Y-%m-%d %H:00:00') ORDER BY 1
            """;
        await using var command = new MySqlCommand(sql, connection, transaction);
        await using var reader = await command.ExecuteReaderAsync(token);
        var rows = new List<HourlyParticipation>();
        while (await reader.ReadAsync(token))
        {
            var utc = DateTime.SpecifyKind(DateTime.ParseExact(reader.GetString(0), "yyyy-MM-dd HH:mm:ss",
                System.Globalization.CultureInfo.InvariantCulture), DateTimeKind.Utc);
            rows.Add(new(utc, reader.GetInt64(1), 0));
        }
        return rows;
    }

    private static List<HourlyParticipation> FillEmptyHours(IReadOnlyList<HourlyParticipation> source,
        ElectionSchedule schedule, DateTime now)
    {
        if (schedule.StartsAt is not { } start || (now < start && source.Count == 0)) return source.ToList();
        var scheduledFinish = schedule.EndsAt is { } end && now > end ? end : now;
        var first = FloorHour(start);
        var last = FloorHour(scheduledFinish);
        // Committee envelopes may be registered after polling closes. All persisted votes belong to
        // the current dataset, so retain outlying buckets instead of hiding recorded activity.
        if (source.Count > 0)
        {
            if (source[0].BucketStart < first) first = source[0].BucketStart;
            if (source[^1].BucketStart > last) last = source[^1].BucketStart;
        }
        var counts = source.ToDictionary(row => row.BucketStart, row => row.Votes);
        var result = new List<HourlyParticipation>();
        for (var bucket = first; bucket <= last; bucket = bucket.AddHours(1))
            result.Add(new(bucket, counts.GetValueOrDefault(bucket), 0));
        return result;
    }

    private static DateTime FloorHour(DateTime value) =>
        new(value.Year, value.Month, value.Day, value.Hour, 0, 0, DateTimeKind.Utc);

}
