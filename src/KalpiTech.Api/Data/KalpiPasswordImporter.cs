using System.Globalization;
using System.Text;
using KalpiTech.Api.Models;
using Microsoft.AspNetCore.Identity;
using Microsoft.VisualBasic.FileIO;
using MySqlConnector;

namespace KalpiTech.Api.Data;

// Runs locally at startup. CSV plaintext never becomes an API response or a log entry.
public sealed class KalpiPasswordImporter(DatabaseConnectionFactory connections, PasswordHasher<LoginAccount> hasher)
{
    public async Task<int> ImportAsync(string path, CancellationToken token)
    {
        var passwords = ReadPasswords(path);
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var transaction = await connection.BeginTransactionAsync(token);
        // Coordinate with imports/voting; a password update does not alter election settings.
        await ElectionStore.ReadRowAsync(connection, transaction, token);
        var accounts = new List<LoginAccount>();
        await using (var command = new MySqlCommand("SELECT KalpiId,KalpiType,PasswordHash FROM Kalpi WHERE KalpiId>0 FOR UPDATE", connection, transaction))
        await using (var reader = await command.ExecuteReaderAsync(token))
            while (await reader.ReadAsync(token))
            {
                var id = reader.GetInt32(0);
                accounts.Add(new(id.ToString(CultureInfo.InvariantCulture), reader.GetString(1), id,
                    reader.IsDBNull(2) ? "" : reader.GetString(2)));
            }
        if (accounts.Count != passwords.Count || accounts.Any(account => !passwords.ContainsKey(account.KalpiId!.Value)))
            throw new InvalidOperationException("קובץ הסיסמאות חייב לכלול בדיוק את כל הקלפיות שבמאגר. לא שונו סיסמאות.");
        var changed = 0;
        foreach (var account in accounts)
        {
            var password = passwords[account.KalpiId!.Value];
            // Keep the existing hash for unchanged passwords, preserving authenticated sessions.
            if (account.PasswordHash.Length > 0 &&
                hasher.VerifyHashedPassword(account, account.PasswordHash, password) != PasswordVerificationResult.Failed) continue;
            await using var update = new MySqlCommand("UPDATE Kalpi SET PasswordHash=@hash WHERE KalpiId=@id", connection, transaction);
            update.Parameters.AddWithValue("@hash", hasher.HashPassword(account, password));
            update.Parameters.AddWithValue("@id", account.KalpiId);
            await update.ExecuteNonQueryAsync(token);
            changed++;
        }
        await transaction.CommitAsync(token);
        return changed;
    }

    internal static Dictionary<int, string> ReadPasswords(string path)
    {
        try
        {
            using var parser = new TextFieldParser(path, new UTF8Encoding(false, true), true)
            { TextFieldType = FieldType.Delimited, HasFieldsEnclosedInQuotes = true, TrimWhiteSpace = false };
            parser.SetDelimiters(",");
            var header = parser.ReadFields();
            var columns = new[] { "KalpiId", "City", "Place", "Address", "KalpiType", "PasswordHash" };
            if (header is null || header.Length != columns.Length || !header.ToHashSet().SetEquals(columns))
                throw new InvalidOperationException("קובץ הקלפיות דורש KalpiId,City,Place,Address,KalpiType,PasswordHash.");
            var idColumn = Array.IndexOf(header, "KalpiId");
            // CSV keeps the user-selected name, but its values are plaintext inputs.
            // Only the database PasswordHash column contains actual hashes.
            var passwordColumn = Array.IndexOf(header, "PasswordHash");
            var result = new Dictionary<int, string>();
            while (!parser.EndOfData)
            {
                var row = parser.ReadFields();
                if (row is null || row.Length != header.Length ||
                    !int.TryParse(row[idColumn].Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out var id) || id <= 0)
                    throw new InvalidOperationException("קובץ הקלפיות מכיל שורה או מספר קלפי שאינם תקינים.");
                var password = row[passwordColumn];
                if (password.Length is < 10 or > 128 || string.IsNullOrWhiteSpace(password) || password.Any(char.IsControl))
                    throw new InvalidOperationException("כל סיסמת קלפי בקובץ חייבת להכיל 10 עד 128 תווים, ללא תווי בקרה.");
                if (!result.TryAdd(id, password)) throw new InvalidOperationException("קובץ הקלפיות מכיל מספר קלפי כפול.");
            }
            if (result.Count == 0) throw new InvalidOperationException("קובץ הקלפיות ריק.");
            return result;
        }
        catch (Exception exception) when (exception is MalformedLineException or DecoderFallbackException or IOException)
        {
            // Parser exceptions may embed a line containing a password: omit their details.
            throw new InvalidOperationException("לא ניתן לקרוא קובץ קלפיות תקין בקידוד UTF-8.");
        }
    }
}
