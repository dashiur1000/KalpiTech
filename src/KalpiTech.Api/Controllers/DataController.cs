using System.Diagnostics;
using System.Text;
using System.Text.Json;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using MySqlConnector;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/data")]
[Authorize(Roles = "Admin")]
public sealed class DataController(DatabaseConnectionFactory connections, ElectionStore elections,
    TimeProvider clock, PasswordHasher<LoginAccount> hasher, IConfiguration configuration,
    IWebHostEnvironment environment) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Read(CancellationToken token)
    {
        var schedule = await elections.ReadAsync(token);
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var command = new MySqlCommand("SELECT (SELECT COUNT(*) FROM Kalpi WHERE KalpiId>0),(SELECT COUNT(*) FROM People),(SELECT COUNT(*) FROM People WHERE Voted=TRUE)", connection);
        await using var reader = await command.ExecuteReaderAsync(token);
        await reader.ReadAsync(token);
        var locked = schedule.InCommitteeWindow(clock.GetUtcNow().UtcDateTime);
        return Ok(new { hasData = reader.GetInt64(0) > 0 || reader.GetInt64(1) > 0,
            canImport = !locked && reader.GetInt64(2) == 0,
            message = locked ? "טעינת הנתונים נעולה למשך 36 שעות ממועד תחילת הבחירות."
                : reader.GetInt64(2) > 0 ? "לא ניתן להחליף מאגר המכיל רישומי הצבעה." : "" });
    }

    [HttpPost("import")]
    [RequestSizeLimit(25_000_000)]
    [RequestFormLimits(MultipartBodyLengthLimit = 25_000_000)]
    public async Task<IActionResult> Import([FromForm] IFormFile kalpiFile, [FromForm] IFormFile peopleFile,
        [FromForm] bool confirmed, CancellationToken token)
    {
        if (!confirmed) return BadRequest(new { message = "יש לאשר את החלפת הנתונים לפני הטעינה." });
        if (kalpiFile.Length == 0 || peopleFile.Length == 0 || kalpiFile.Length > 5_000_000 || peopleFile.Length > 20_000_000)
            return BadRequest(new { message = "יש לבחור שני קובצי CSV: קלפיות עד 5 MB ובוחרים עד 20 MB." });
        var root = Path.GetFullPath(Path.Combine(environment.ContentRootPath, "..", ".."));
        var directory = Path.Combine(root, ".local", "uploads", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            // Ignore client filenames: only generated private paths are used.
            await using (var file = System.IO.File.Create(Path.Combine(directory, "kalpi.csv"))) await kalpiFile.CopyToAsync(file, token);
            await using (var file = System.IO.File.Create(Path.Combine(directory, "people.csv"))) await peopleFile.CopyToAsync(file, token);
            var passwords = KalpiPasswordImporter.ReadPasswords(Path.Combine(directory, "kalpi.csv"));
            var hashes = passwords.ToDictionary(pair => pair.Key.ToString(System.Globalization.CultureInfo.InvariantCulture),
                pair => hasher.HashPassword(new LoginAccount(pair.Key.ToString(), "Regular", pair.Key, ""), pair.Value));
            await System.IO.File.WriteAllTextAsync(Path.Combine(directory, "hashes.json"), JsonSerializer.Serialize(hashes), token);
            var start = new ProcessStartInfo(configuration["DataLoader:PythonPath"] ?? Path.Combine(root, ".venv", "Scripts", "python.exe"))
            { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
            start.ArgumentList.Add(Path.Combine(root, "tools", "data_loader", "replace.py"));
            start.ArgumentList.Add(directory);
            foreach (var key in new[] { "MYSQL_HOST", "MYSQL_PASSWORD", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER" })
                if (configuration[key] is { } value) start.Environment[key] = value;
            using var process = Process.Start(start) ?? throw new IOException();
            // Do not cancel a running transaction on a browser disconnect. Wait for its result.
            var output = process.StandardOutput.ReadToEndAsync();
            var errors = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            await errors; // Drain without logging potentially sensitive runtime diagnostics.
            using var result = JsonDocument.Parse(await output);
            return StatusCode(result.RootElement.GetProperty("status").GetInt32(), result.RootElement.Clone());
        }
        catch (InvalidOperationException error) { return BadRequest(new { message = error.Message }); }
        catch (Exception error) when (error is IOException or System.ComponentModel.Win32Exception or JsonException)
        { return StatusCode(503, new { message = "הטעינה לא קיבלה אישור הצלחה. יש לבדוק את המאגר לפני ניסיון נוסף." }); }
        finally { Directory.Delete(directory, true); }
    }
}
