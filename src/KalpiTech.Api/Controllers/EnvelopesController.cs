using System.Security.Claims;
using System.Text.RegularExpressions;
using KalpiTech.Api.Contracts;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using KalpiTech.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/envelopes")]
[Authorize(Roles = "Admin")]
public sealed class EnvelopesController(VoterStore voters, VoteStore votes, ElectionStore elections,
    TimeProvider clock, VoteConfirmationEmail emails, AuditLogStore audit) : ControllerBase
{
    private const string WindowMessage = "הזנת מעטפות כפולות אפשרית רק בתוך 36 שעות ממועד תחילת הבחירות.";
    private static bool ValidId(string? id) => id is not null && Regex.IsMatch(id, "\\A[0-9]{9}\\z");

    // POST keeps identity numbers out of the URL; the existing CSRF filter applies.
    [HttpPost("search")]
    public async Task<IActionResult> Search(VoterSearchRequest request, CancellationToken token)
    {
        if (!ValidId(request.Id)) return BadRequest(new { message = "מספר הזהות חייב להכיל תשע ספרות." });
        var schedule = await elections.ReadAsync(token);
        if (!schedule.InCommitteeWindow(clock.GetUtcNow().UtcDateTime))
        {
            await WriteAudit(AuditResults.Blocked, request.Id!, "חיפוש מחוץ לחלון 36 השעות", token);
            return Conflict(new { message = WindowMessage });
        }
        var voter = await voters.FindAsync(request.Id!, token);
        if (voter is null)
        {
            await WriteAudit(AuditResults.Blocked, request.Id!, "מספר זהות אינו קיים", token);
            return NotFound(new { message = "שגיאה מספר הזהות אינו במאגר" });
        }
        if (voter.Voted)
        {
            await WriteAudit(AuditResults.Blocked, request.Id!, "הבוחר כבר הצביע", token);
            return Conflict(new { message = "הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה" });
        }
        await WriteAudit(AuditResults.Success, request.Id!, "הבוחר נמצא למעטפה כפולה", token);
        return Ok(new { voter.Id, voter.FirstName, voter.LastName, voter.KalpiId });
    }

    [HttpPost("confirm")]
    public async Task<IActionResult> Confirm(VoterSearchRequest request, CancellationToken token)
    {
        if (!ValidId(request.Id)) return BadRequest(new { message = "מספר הזהות חייב להכיל תשע ספרות." });
        var actor = User.FindFirstValue(ClaimTypes.NameIdentifier)!;
        var result = await votes.ConfirmEnvelopeAsync(request.Id!, actor, HttpContext.TraceIdentifier, token);
        await emails.SendAsync(result, "Admin", actor, request.Id!, HttpContext.TraceIdentifier);
        return result.Status switch
        {
            VoteStatus.Saved => Ok(new { message = "ההצבעה נקלטה בהצלחה!", result.VotedAt, votedIn = 0, votedInLabel = "0000 — ועדת הבחירות" }),
            VoteStatus.CommitteeWindowClosed => Conflict(new { message = WindowMessage }),
            VoteStatus.NotFound => NotFound(new { message = "שגיאה מספר הזהות אינו במאגר" }),
            _ => Conflict(new { message = "שגיאה! הבוחר כבר הצביע ככל הנראה במקום אחר" })
        };
    }

    private Task WriteAudit(string result, string id, string details, CancellationToken token) =>
        audit.WriteAsync(new(AuditActions.DoubleEnvelope, result, "Admin",
            User.FindFirstValue(ClaimTypes.NameIdentifier), "Voter", id, details, HttpContext.TraceIdentifier), token);
}
