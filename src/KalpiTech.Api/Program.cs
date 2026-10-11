using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using KalpiTech.Api.Services;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using MySqlConnector;

var builder = WebApplication.CreateBuilder(args.Where(arg => arg != "--import-kalpi-passwords").ToArray());
// Console logging works locally without permission to write to Windows Event Log.
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Services.AddSingleton<DatabaseConnectionFactory>();
builder.Services.AddSingleton<DatabaseProbe>();
builder.Services.AddScoped<AccountStore>();
builder.Services.AddScoped<KalpiPasswordImporter>();
builder.Services.AddScoped<VoterStore>();
builder.Services.AddScoped<VoteStore>();
builder.Services.AddScoped<ElectionStore>();
builder.Services.AddScoped<StatisticsStore>();
VoteConfirmationEmail.ValidateConfiguration(builder.Configuration);
builder.Services.AddHttpClient<VoteConfirmationEmail>(client =>
{
    client.BaseAddress = new Uri("https://api.brevo.com/v3/");
    // Integration tests may use only a loopback emulator, never a replacement external endpoint.
    if (builder.Environment.IsEnvironment("Testing") && builder.Configuration["Mail:TestBaseUrl"] is { } testUrl)
    {
        var uri = new Uri(testUrl);
        if (!uri.IsLoopback || uri.Scheme != "http") throw new InvalidOperationException("Email test endpoint must be local HTTP.");
        client.BaseAddress = uri;
    }
    client.Timeout = TimeSpan.FromSeconds(5);
});
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddScoped<AccountCookies>();
builder.Services.AddSingleton<PasswordHasher<LoginAccount>>();
// MVC's built-in CSRF filter needs the services supplied by AddControllersWithViews.
builder.Services.AddControllersWithViews(options => options.Filters.Add(new AutoValidateAntiforgeryTokenAttribute()))
    .ConfigureApiBehaviorOptions(options => options.InvalidModelStateResponseFactory = _ =>
        new BadRequestObjectResult(new { message = "יש למלא את השדות הנדרשים בצורה תקינה." }));
builder.Services.AddAntiforgery(options =>
{
    options.HeaderName = "X-CSRF-TOKEN";
    options.Cookie.Name = "KalpiTech.Csrf";
    options.Cookie.SameSite = SameSiteMode.Strict;
});
var keysDirectory = builder.Configuration["DataProtection:KeyPath"]
    ?? Path.GetFullPath(Path.Combine(builder.Environment.ContentRootPath, "..", "..", ".local", "keys"));
var protection = builder.Services.AddDataProtection().SetApplicationName("KalpiTech")
    .PersistKeysToFileSystem(new DirectoryInfo(keysDirectory));
if (OperatingSystem.IsWindows()) protection.ProtectKeysWithDpapi();
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie(options =>
{
    options.Cookie.Name = "KalpiTech.Auth";
    options.Cookie.HttpOnly = true;
    options.Cookie.SameSite = SameSiteMode.Strict;
    // Local HTTP only for development; HTTPS deployment will always use Secure cookies.
    options.Cookie.SecurePolicy = CookieSecurePolicy.SameAsRequest;
    options.ExpireTimeSpan = TimeSpan.FromHours(8);
    options.SlidingExpiration = false;
    options.EventsType = typeof(AccountCookies);
});
builder.Services.AddAuthorization();

var app = builder.Build();
var importOnly = args.Contains("--import-kalpi-passwords", StringComparer.Ordinal);
// Validate required configuration at startup rather than on the first request.
_ = app.Services.GetRequiredService<DatabaseProbe>();
using (var scope = app.Services.CreateScope())
{
    await scope.ServiceProvider.GetRequiredService<AccountStore>().InitializeAdminAsync(builder.Configuration, CancellationToken.None);
    var passwordCsv = builder.Configuration["KalpiPasswords:Path"]
        ?? Path.GetFullPath(Path.Combine(builder.Environment.ContentRootPath, "..", "..", ".local", "import", "kalpi.csv"));
    await using var importConnection = scope.ServiceProvider.GetRequiredService<DatabaseConnectionFactory>().Create();
    await importConnection.OpenAsync();
    await using var importState = new MySqlCommand("SELECT COUNT(*) FROM DataImportState", importConnection);
    var uploadedDataset = Convert.ToInt32(await importState.ExecuteScalarAsync()) > 0;
    if (uploadedDataset && !importOnly)
        app.Logger.LogInformation("Uploaded dataset preserved, including station passwords.");
    else if (File.Exists(passwordCsv))
    {
        var changed = await scope.ServiceProvider.GetRequiredService<KalpiPasswordImporter>().ImportAsync(passwordCsv, CancellationToken.None);
        app.Logger.LogInformation("Kalpi password import completed. Changed accounts: {Count}.", changed);
    }
    else if (importOnly) throw new InvalidOperationException("חסר קובץ הקלפיות המקומי לטעינת סיסמאות.");
    else app.Logger.LogInformation("Kalpi password CSV is absent; existing station passwords were preserved.");
}
// Local one-shot import: no HTTP listener and no reset of existing accounts or votes.
if (importOnly) return;

app.Use(async (context, next) =>
{
    if (context.Request.Path.StartsWithSegments("/api")) context.Response.Headers.CacheControl = "no-store";
    try { await next(context); }
    catch (Exception exception) when (exception is MySqlException or TimeoutException)
    {
        app.Logger.LogWarning("Database request failed ({ExceptionType}).", exception.GetType().Name);
        context.Response.StatusCode = 503;
        await context.Response.WriteAsJsonAsync(new { message = "השרת אינו זמין" });
    }
});
app.UseDefaultFiles();
app.UseStaticFiles();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();

// Liveness: the API can answer even when MySQL is unavailable.
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

// Readiness: open a real connection and execute a harmless SQL query.
app.MapGet("/health/db", async (DatabaseProbe database, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
{
    try
    {
        await database.CheckAsync(cancellationToken);
        return Results.Ok(new { status = "ok", database = "VotesDb" });
    }
    catch (Exception exception) when (exception is MySqlException or TimeoutException)
    {
        // Do not return connection credentials or SQL exception details to the client.
        logger.LogWarning("Database health check failed ({ExceptionType}).", exception.GetType().Name);
        return Results.Json(new { status = "unavailable", message = "השרת אינו זמין" },
            statusCode: StatusCodes.Status503ServiceUnavailable);
    }
});

app.Run();
