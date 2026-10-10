using System.Globalization;
using KalpiTech.Api.Models;
using Microsoft.AspNetCore.Identity;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class AccountStore(DatabaseConnectionFactory connections, PasswordHasher<LoginAccount> hasher)
{
    public async Task<LoginAccount?> FindAsync(string identifier, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        if (int.TryParse(identifier, NumberStyles.None, CultureInfo.InvariantCulture, out var kalpiId) && kalpiId > 0)
        {
            await using var command = new MySqlCommand("SELECT KalpiType,PasswordHash FROM Kalpi WHERE KalpiId=@id", connection);
            command.Parameters.AddWithValue("@id", kalpiId);
            await using var reader = await command.ExecuteReaderAsync(token);
            if (!await reader.ReadAsync(token) || reader.IsDBNull(1)) return null;
            return new(kalpiId.ToString(CultureInfo.InvariantCulture), reader.GetString(0), kalpiId, reader.GetString(1));
        }
        await using var adminCommand = new MySqlCommand("SELECT EmailAddress,PasswordHash FROM AdminAccount WHERE Id=1", connection);
        await using var adminReader = await adminCommand.ExecuteReaderAsync(token);
        if (!await adminReader.ReadAsync(token) || !string.Equals(identifier, adminReader.GetString(0), StringComparison.OrdinalIgnoreCase))
            return null;
        return new(adminReader.GetString(0), "Admin", null, adminReader.GetString(1));
    }

    public async Task InitializeAdminAsync(IConfiguration configuration, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var exists = new MySqlCommand("SELECT COUNT(*) FROM AdminAccount WHERE Id=1", connection);
        if (Convert.ToInt32(await exists.ExecuteScalarAsync(token)) != 0) return;
        var email = configuration["ADMIN_EMAIL"];
        var password = configuration["ADMIN_INITIAL_PASSWORD"];
        if (string.IsNullOrWhiteSpace(email) || email.Length > 254 || !new System.ComponentModel.DataAnnotations.EmailAddressAttribute().IsValid(email)
            || password is null || password.Length is < 12 or > 128 || password.StartsWith("replace_with_", StringComparison.Ordinal))
            throw new InvalidOperationException("Set ADMIN_EMAIL and ADMIN_INITIAL_PASSWORD (12-128 characters) for first startup.");
        var account = new LoginAccount(email, "Admin", null, "");
        await using var insert = new MySqlCommand("INSERT INTO AdminAccount (Id,EmailAddress,PasswordHash) VALUES (1,@email,@hash) ON DUPLICATE KEY UPDATE Id=Id", connection);
        insert.Parameters.AddWithValue("@email", email);
        insert.Parameters.AddWithValue("@hash", hasher.HashPassword(account, password));
        await insert.ExecuteNonQueryAsync(token);
    }

    public async Task<bool> ChangeAdminPasswordAsync(LoginAccount account, string newPassword, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var command = new MySqlCommand("UPDATE AdminAccount SET PasswordHash=@hash WHERE Id=1 AND PasswordHash=@previous", connection);
        command.Parameters.AddWithValue("@hash", hasher.HashPassword(account, newPassword));
        command.Parameters.AddWithValue("@previous", account.PasswordHash);
        return await command.ExecuteNonQueryAsync(token) == 1;
    }

    public async Task<bool> SetKalpiPasswordAsync(int kalpiId, string newPassword, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        var account = new LoginAccount(kalpiId.ToString(CultureInfo.InvariantCulture), "", kalpiId, "");
        await using var command = new MySqlCommand("UPDATE Kalpi SET PasswordHash=@hash WHERE KalpiId=@id", connection);
        command.Parameters.AddWithValue("@hash", hasher.HashPassword(account, newPassword));
        command.Parameters.AddWithValue("@id", kalpiId);
        return await command.ExecuteNonQueryAsync(token) == 1;
    }
}
