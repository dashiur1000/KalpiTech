using KalpiTech.Api.Data;
using MySqlConnector;

var builder = WebApplication.CreateBuilder(args);
// Console logging works locally without permission to write to Windows Event Log.
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Services.AddSingleton<DatabaseProbe>();

var app = builder.Build();
// Validate required configuration at startup rather than on the first request.
_ = app.Services.GetRequiredService<DatabaseProbe>();

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
