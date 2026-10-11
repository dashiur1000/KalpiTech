using KalpiTech.Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/statistics")]
[Authorize(Roles = "Admin")]
public sealed class StatisticsController(StatisticsStore statistics) : ControllerBase
{
    // Aggregated counts only: no identity numbers, voter names, email or passwords.
    [HttpGet]
    public async Task<IActionResult> Read(CancellationToken token) => Ok(await statistics.ReadAsync(token));
}
