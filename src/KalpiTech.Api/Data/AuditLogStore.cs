using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class AuditLogStore(DatabaseConnectionFactory connections, TimeProvider clock,
    ILogger<AuditLogStore> logger)
{
    public async Task WriteAsync(AuditEvent entry, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await InsertAsync(connection, null, entry, clock.GetUtcNow().UtcDateTime, token);
    }

    public async Task TryWriteAsync(AuditEvent entry)
    {
        try { await WriteAsync(entry, CancellationToken.None); }
        catch (Exception error) when (error is MySqlException or TimeoutException)
        {
            logger.LogWarning("Audit event could not be stored ({ExceptionType}).", error.GetType().Name);
        }
    }

    public Task WriteAsync(MySqlConnection connection, MySqlTransaction transaction,
        AuditEvent entry, CancellationToken token) =>
        InsertAsync(connection, transaction, entry, clock.GetUtcNow().UtcDateTime, token);

    private static async Task InsertAsync(MySqlConnection connection, MySqlTransaction? transaction,
        AuditEvent entry, DateTime occurredAt, CancellationToken token)
    {
        static string? Limit(string? value, int length) => string.IsNullOrWhiteSpace(value)
            ? null : value.Trim()[..Math.Min(value.Trim().Length, length)];
        await using var command = new MySqlCommand(
            "INSERT INTO AuditLogs (OccurredAtUtc,ActorRole,ActorIdentifier,Action,TargetType,TargetIdentifier,Result,Details,CorrelationId) " +
            "VALUES (@at,@role,@actor,@action,@type,@target,@result,@details,@correlation)", connection, transaction);
        command.Parameters.AddWithValue("@at", occurredAt);
        command.Parameters.AddWithValue("@role", (object?)Limit(entry.ActorRole, 32) ?? DBNull.Value);
        command.Parameters.AddWithValue("@actor", (object?)Limit(entry.ActorIdentifier, 254) ?? DBNull.Value);
        command.Parameters.AddWithValue("@action", Limit(entry.Action, 64)!);
        command.Parameters.AddWithValue("@type", (object?)Limit(entry.TargetType, 32) ?? DBNull.Value);
        command.Parameters.AddWithValue("@target", (object?)Limit(entry.TargetIdentifier, 128) ?? DBNull.Value);
        command.Parameters.AddWithValue("@result", Limit(entry.Result, 32)!);
        command.Parameters.AddWithValue("@details", (object?)Limit(entry.Details, 1000) ?? DBNull.Value);
        command.Parameters.AddWithValue("@correlation", Guid.TryParse(entry.CorrelationId, out var correlation)
            ? correlation.ToString() : DBNull.Value);
        await command.ExecuteNonQueryAsync(token);
    }

    public async Task<AuditLogPage> ReadAsync(int page, int pageSize, string? action, string? result,
        string? actorIdentifier, DateTimeOffset? from, DateTimeOffset? to, CancellationToken token)
    {
        page = Math.Max(1, page);
        pageSize = Math.Clamp(pageSize, 1, 100);
        var clauses = new List<string>();
        var parameters = new List<MySqlParameter>();
        void Add(string clause, string name, object value)
        {
            clauses.Add(clause); parameters.Add(new MySqlParameter(name, value));
        }
        if (!string.IsNullOrWhiteSpace(action)) Add("Action=@action", "@action", action.Trim());
        if (!string.IsNullOrWhiteSpace(result)) Add("Result=@result", "@result", result.Trim());
        if (!string.IsNullOrWhiteSpace(actorIdentifier)) Add("ActorIdentifier=@actor", "@actor", actorIdentifier.Trim());
        if (from is not null) Add("OccurredAtUtc>=@from", "@from", from.Value.UtcDateTime);
        if (to is not null) Add("OccurredAtUtc<=@to", "@to", to.Value.UtcDateTime);
        var where = clauses.Count == 0 ? "" : " WHERE " + string.Join(" AND ", clauses);
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var count = new MySqlCommand("SELECT COUNT(*) FROM AuditLogs" + where, connection);
        count.Parameters.AddRange(parameters.Select(p => new MySqlParameter(p.ParameterName, p.Value)).ToArray());
        var total = Convert.ToInt64(await count.ExecuteScalarAsync(token));
        await using var command = new MySqlCommand(
            "SELECT Id,OccurredAtUtc,ActorRole,ActorIdentifier,Action,TargetType,TargetIdentifier,Result,Details,CorrelationId " +
            "FROM AuditLogs" + where + " ORDER BY OccurredAtUtc DESC,Id DESC LIMIT @limit OFFSET @offset", connection);
        command.Parameters.AddRange(parameters.ToArray());
        command.Parameters.AddWithValue("@limit", pageSize);
        command.Parameters.AddWithValue("@offset", (page - 1) * pageSize);
        var items = new List<AuditLogItem>();
        await using var reader = await command.ExecuteReaderAsync(token);
        while (await reader.ReadAsync(token))
        {
            var actorRole = reader.IsDBNull(2) ? null : reader.GetString(2);
            var actor = reader.IsDBNull(3) ? null : reader.GetString(3);
            if (actorRole is null && actor is { Length: 9 } && actor.All(char.IsAsciiDigit))
                actor = new string('*', 5) + actor[^4..];
            var targetType = reader.IsDBNull(5) ? null : reader.GetString(5);
            var target = reader.IsDBNull(6) ? null : reader.GetString(6);
            if ((targetType == "Voter" || target is { Length: 9 } && target.All(char.IsAsciiDigit)) && target is { Length: >= 4 })
                target = new string('*', target.Length - 4) + target[^4..];
            items.Add(new(reader.GetInt64(0), reader.GetDateTime(1),
                actorRole, actor,
                reader.GetString(4), targetType, target, reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                reader.IsDBNull(9) ? null : Convert.ToString(reader.GetValue(9), System.Globalization.CultureInfo.InvariantCulture)));
        }
        return new(items, page, pageSize, total, total == 0 ? 0 : (int)Math.Ceiling(total / (double)pageSize));
    }
}
