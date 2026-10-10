using MySqlConnector;

namespace KalpiTech.Api.Data;

// Owns only the connection check. Business tables and rules come in later stages.
public sealed class DatabaseProbe
{
    private readonly DatabaseConnectionFactory connections;

    public DatabaseProbe(DatabaseConnectionFactory connections) => this.connections = connections;

    public async Task CheckAsync(CancellationToken cancellationToken)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(cancellationToken);
        await using var command = new MySqlCommand("SELECT 1", connection);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        if (Convert.ToInt32(result) != 1)
            throw new InvalidOperationException("Unexpected database health check result.");
    }
}
