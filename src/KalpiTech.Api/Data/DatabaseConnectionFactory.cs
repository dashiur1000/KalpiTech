using MySqlConnector;

namespace KalpiTech.Api.Data;

// A shared connection configuration; each operation owns and disposes its connection.
public sealed class DatabaseConnectionFactory
{
    private readonly string connectionString;

    public DatabaseConnectionFactory(IConfiguration configuration)
    {
        var password = configuration["MYSQL_PASSWORD"];
        if (string.IsNullOrWhiteSpace(password))
            throw new InvalidOperationException("MYSQL_PASSWORD must be configured before starting the API.");
        if (!uint.TryParse(configuration["MYSQL_PORT"] ?? "3307", out var port) || port is 0 or > 65535)
            throw new InvalidOperationException("MYSQL_PORT must be between 1 and 65535.");
        connectionString = new MySqlConnectionStringBuilder
        {
            Server = "127.0.0.1", Port = port,
            Database = configuration["MYSQL_DATABASE"] ?? "VotesDb",
            UserID = configuration["MYSQL_USER"] ?? "kalpitech", Password = password,
            ConnectionTimeout = 3, DefaultCommandTimeout = 5, DateTimeKind = MySqlDateTimeKind.Utc
        }.ConnectionString;
    }

    public MySqlConnection Create() => new(connectionString);
}
