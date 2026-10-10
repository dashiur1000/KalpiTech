using KalpiTech.Api.Contracts;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using KalpiTech.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/election")]
[Authorize]
public sealed class ElectionController(ElectionStore elections, TimeProvider clock) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Read(CancellationToken token)
    {
        var schedule = await elections.ReadAsync(token);
        var now = clock.GetUtcNow().UtcDateTime;
        return Ok(new {
            schedule.StartsAt, schedule.EndsAt, schedule.LoadLockedUntil,
            startsAtIsrael = IsraelTime.Format(schedule.StartsAt), endsAtIsrael = IsraelTime.Format(schedule.EndsAt),
            loadLockedUntilIsrael = IsraelTime.Format(schedule.LoadLockedUntil),
            state = schedule.State(now), canEdit = !schedule.HasStarted(now),
            loadLocked = schedule.InCommitteeWindow(now),
            doubleEnvelopesAllowed = schedule.InCommitteeWindow(now), serverTime = now
        });
    }

    [HttpPost("schedule")]
    [Authorize(Roles = "Admin")]
    public async Task<IActionResult> Save(ElectionScheduleRequest request, CancellationToken token)
    {
        if (!IsraelTime.TryParse(request.StartsAt, out var start) || !IsraelTime.TryParse(request.EndsAt, out var end))
            return BadRequest(new { message = "יש להזין תאריך ושעה תקינים לפי שעון ישראל. שעה שאינה קיימת או מופיעה פעמיים במעבר שעון אינה נתמכת." });
        if (end <= start) return BadRequest(new { message = "מועד הסיום חייב להיות מאוחר ממועד ההתחלה." });
        var error = await elections.SaveAsync(new ElectionSchedule(start, end), token);
        if (error is not null) return Conflict(new { message = error });
        return Ok(new { message = "מועדי הבחירות נשמרו בהצלחה." });
    }
}
