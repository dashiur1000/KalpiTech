using System.Security.Claims;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/statistics")]
[Authorize(Roles = "Admin")]
public sealed class StatisticsController(StatisticsStore statistics, AuditLogStore audit) : ControllerBase
{
    // Aggregated counts only: no identity numbers, voter names, email or passwords.
    [HttpGet]
    public async Task<IActionResult> Read([FromQuery] bool recordView = true, CancellationToken token = default)
    {
        var report = await statistics.ReadAsync(token);
        // The dashboard refreshes every five seconds. Record opening the view, not every automatic refresh.
        if (recordView)
            await audit.TryWriteAsync(new(AuditActions.StatisticsView, AuditResults.Success,
                User.FindFirstValue(ClaimTypes.Role), User.FindFirstValue(ClaimTypes.NameIdentifier),
                "Statistics", null, "צפייה בנתוני ההשתתפות", HttpContext.TraceIdentifier));
        return Ok(report);
    }
}
