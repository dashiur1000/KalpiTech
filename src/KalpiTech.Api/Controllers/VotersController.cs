using System.Security.Claims;
using System.Text.RegularExpressions;
using KalpiTech.Api.Contracts;
using KalpiTech.Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/voters")]
[Authorize(Roles = "Regular,Accessible")]
public sealed class VotersController(VoterStore voters) : ControllerBase
{
    // POST keeps the identity number out of URLs and normal access logs.
    // The global CSRF filter also applies to this authenticated request.
    [HttpPost("search")]
    public async Task<IActionResult> Search(VoterSearchRequest request, CancellationToken token)
    {
        if (request.Id is null || !Regex.IsMatch(request.Id, "\\A[0-9]{9}\\z"))
            return BadRequest(new { message = "מספר הזהות חייב להכיל תשע ספרות." });

        var voter = await voters.FindAsync(request.Id, token);
        if (voter is null)
            return NotFound(new { message = "שגיאה מספר הזהות אינו במאגר" });

        // The assignment check precedes the vote-status check, as required by README.
        if (User.IsInRole("Regular") &&
            (!int.TryParse(User.FindFirstValue("KalpiId"), out var connectedKalpi) || voter.KalpiId != connectedKalpi))
            return StatusCode(403, new { message = "הבוחר אינו משתייך לקלפי זה" });

        if (voter.Voted)
            return Conflict(new { message = "הצבעה כפולה! הבוחר כבר מימש את זכות הבחירה" });

        // No vote mutation and no email/history fields in the response.
        return Ok(new { voter.Id, voter.FirstName, voter.LastName, voter.KalpiId });
    }
}
