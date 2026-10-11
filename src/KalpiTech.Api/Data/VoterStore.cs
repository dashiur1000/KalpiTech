using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class VoterStore(DatabaseConnectionFactory connections)
{
    public async Task<Voter?> FindAsync(string id, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var command = new MySqlCommand(
            "SELECT Id,KalpiId,FirstName,LastName,Voted FROM People WHERE Id=@id", connection);
        command.Parameters.AddWithValue("@id", id);
        await using var reader = await command.ExecuteReaderAsync(token);
        if (!await reader.ReadAsync(token)) return null;
        return new(reader.GetString(0), reader.GetInt32(1), reader.GetString(2), reader.GetString(3), reader.GetBoolean(4));
    }
}
