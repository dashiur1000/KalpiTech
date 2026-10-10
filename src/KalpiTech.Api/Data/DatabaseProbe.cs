using MySqlConnector;

namespace KalpiTech.Api.Data;

// Owns only the connection check. Business tables and rules come in later stages.
public sealed class DatabaseProbe
{
    private readonly string connectionString;

    public DatabaseProbe(IConfiguration configuration)
    {
        var password = configuration["MYSQL_PASSWORD"];
        if (string.IsNullOrWhiteSpace(password))
            throw new InvalidOperationException("MYSQL_PASSWORD must be configured before starting the API.");

        var portText = configuration["MYSQL_PORT"] ?? "3307";
        if (!uint.TryParse(portText, out var port) || port is 0 or > 65535)
            throw new InvalidOperationException("MYSQL_PORT must be between 1 and 65535.");

        // The builder safely escapes credentials in the connection string.
        connectionString = new MySqlConnectionStringBuilder
        {
            Server = "127.0.0.1",
            Port = port,
            Database = "VotesDb",
            UserID = "kalpitech",
            Password = password,
            ConnectionTimeout = 3,
            DefaultCommandTimeout = 3
        }.ConnectionString;
    }

    public async Task CheckAsync(CancellationToken cancellationToken)
    {
        await using var connection = new MySqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new MySqlCommand("SELECT 1", connection);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        if (Convert.ToInt32(result) != 1)
            throw new InvalidOperationException("Unexpected database health check result.");
    }
}
