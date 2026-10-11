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
public sealed class EnvelopesController(VoterStore voters, VoteStore votes, ElectionStore elections, TimeProvider clock, VoteConfirmationEmail emails) : ControllerBase
{
    private const string WindowMessage = "הזנת מעטפות כפולות אפשרית רק בתוך 36 שעות ממועד תחילת הבחירות.";
    private static bool ValidId(string? id) => id is not null && Regex.IsMatch(id, "\\A[0-9]{9}\\z");

    // POST keeps identity numbers out of the URL; the existing CSRF filter applies.
    [HttpPost("search")]
    public async Task<IActionResult> Search(VoterSearchRequest request, CancellationToken token)
    {
        if (!ValidId(request.Id)) return BadRequest(new { message = "מספר הזהות חייב להכיל תשע ספרות." });
        var schedule = await elections.ReadAsync(token);
        if (!schedule.InCommitteeWindow(clock.GetUtcNow().UtcDateTime)) return Conflict(new { message = WindowMessage });
        var voter = await voters.FindAsync(request.Id!, token);
        if (voter is null) return NotFound(new { message = "שגיאה מספר הזהות אינו במאגר" });
        if (voter.Voted) return Conflict(new { message = "הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה" });
        return Ok(new { voter.Id, voter.FirstName, voter.LastName, voter.KalpiId });
    }

    [HttpPost("confirm")]
    public async Task<IActionResult> Confirm(VoterSearchRequest request, CancellationToken token)
    {
        if (!ValidId(request.Id)) return BadRequest(new { message = "מספר הזהות חייב להכיל תשע ספרות." });
        var result = await votes.ConfirmEnvelopeAsync(request.Id!, token);
        await emails.SendAsync(result);
        return result.Status switch
        {
            VoteStatus.Saved => Ok(new { message = "ההצבעה נקלטה בהצלחה!", result.VotedAt, votedIn = 0, votedInLabel = "0000 — ועדת הבחירות" }),
            VoteStatus.CommitteeWindowClosed => Conflict(new { message = WindowMessage }),
            VoteStatus.NotFound => NotFound(new { message = "שגיאה מספר הזהות אינו במאגר" }),
            _ => Conflict(new { message = "שגיאה! הבוחר כבר הצביע ככל הנראה במקום אחר" })
        };
    }
}
