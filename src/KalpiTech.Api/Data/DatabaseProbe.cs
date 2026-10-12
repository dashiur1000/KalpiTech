using MySqlConnector;

namespace KalpiTech.Api.Data;

// Separates database connectivity from station account readiness.
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

    public async Task<bool> HasStationPasswordsAsync(CancellationToken cancellationToken)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(cancellationToken);
        await using var command = new MySqlCommand(
            "SELECT EXISTS(SELECT 1 FROM Kalpi WHERE KalpiId>0 AND PasswordHash IS NOT NULL AND TRIM(PasswordHash)<>'')", connection);
        return Convert.ToInt32(await command.ExecuteScalarAsync(cancellationToken)) == 1;
    }
}
