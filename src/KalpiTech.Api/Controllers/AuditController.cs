using System.Security.Claims;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/audit")]
[Authorize(Roles = "Admin")]
public sealed class AuditController(AuditLogStore audit) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Read([FromQuery] int page = 1, [FromQuery] int pageSize = 25,
        [FromQuery] string? action = null, [FromQuery] string? result = null,
        [FromQuery] string? actorIdentifier = null, [FromQuery] DateTimeOffset? from = null,
        [FromQuery] DateTimeOffset? to = null, [FromQuery] bool recordView = true,
        CancellationToken token = default)
    {
        if (page < 1 || pageSize is < 1 or > 100 || (from is not null && to is not null && from > to))
            return BadRequest(new { message = "פרמטרי הסינון או העימוד אינם תקינים." });
        // Filters and pagination do not create endless self-referential entries; opening the view is recorded once.
        if (recordView)
            await audit.TryWriteAsync(new(AuditActions.AuditView, AuditResults.Success,
                User.FindFirstValue(ClaimTypes.Role), User.FindFirstValue(ClaimTypes.NameIdentifier),
                "AuditLog", null, "צפייה ביומן הפעולות", HttpContext.TraceIdentifier));
        var resultPage = await audit.ReadAsync(page, pageSize, action, result, actorIdentifier, from, to, token);
        return Ok(resultPage);
    }
}
