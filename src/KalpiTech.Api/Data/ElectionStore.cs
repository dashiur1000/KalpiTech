using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class ElectionStore(DatabaseConnectionFactory connections, TimeProvider clock)
{
    public async Task<ElectionSchedule> ReadAsync(CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        return await ReadRowAsync(connection, null, token);
    }

    // Lock the singleton row before checking time, so concurrent changes are serialized.
    public async Task<string?> SaveAsync(ElectionSchedule schedule, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var transaction = await connection.BeginTransactionAsync(token);
        var current = await ReadRowAsync(connection, transaction, token);
        var now = clock.GetUtcNow().UtcDateTime;
        if (current.HasStarted(now)) return "לא ניתן לשנות את המועדים לאחר תחילת הבחירות.";
        if (schedule.StartsAt <= now) return "מועד תחילת הבחירות חייב להיות בעתיד.";
        await using var command = new MySqlCommand(
            "UPDATE ElectionSettings SET StartsAt=@start,EndsAt=@end WHERE Id=1", connection, transaction);
        command.Parameters.AddWithValue("@start", schedule.StartsAt);
        command.Parameters.AddWithValue("@end", schedule.EndsAt);
        await command.ExecuteNonQueryAsync(token);
        await transaction.CommitAsync(token);
        return null;
    }

    private static async Task<ElectionSchedule> ReadRowAsync(MySqlConnection connection,
        MySqlTransaction? transaction, CancellationToken token)
    {
        await using var command = new MySqlCommand(
            "SELECT StartsAt,EndsAt FROM ElectionSettings WHERE Id=1" +
            (transaction is null ? "" : " FOR UPDATE"), connection, transaction);
        await using var reader = await command.ExecuteReaderAsync(token);
        if (!await reader.ReadAsync(token)) throw new InvalidOperationException("ElectionSettings row is missing.");
        return new(reader.IsDBNull(0) ? null : reader.GetDateTime(0),
            reader.IsDBNull(1) ? null : reader.GetDateTime(1));
    }
}
