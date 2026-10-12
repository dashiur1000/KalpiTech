using System.Security.Claims;
using KalpiTech.Api.Contracts;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using KalpiTech.Api.Services;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;

namespace KalpiTech.Api.Controllers;

[ApiController]
[Route("api/auth")]
public sealed class AuthController(AccountStore accounts, PasswordHasher<LoginAccount> hasher,
    IAntiforgery antiforgery, AuditLogStore audit) : ControllerBase
{
    [HttpGet("csrf")]
    public IActionResult Csrf() => Ok(new { token = antiforgery.GetAndStoreTokens(HttpContext).RequestToken });

    [HttpPost("login")]
    public async Task<IActionResult> Login(LoginRequest request, CancellationToken token)
    {
        var identifier = request.Identifier.Trim();
        var account = await accounts.FindAsync(identifier, token);
        if (account is null || hasher.VerifyHashedPassword(account, account.PasswordHash, request.Password) == PasswordVerificationResult.Failed)
        {
            await audit.WriteAsync(new(AuditActions.Login, AuditResults.Failed, null, identifier,
                "Account", identifier, "פרטי התחברות אינם תקינים", HttpContext.TraceIdentifier), token);
            return Unauthorized(new { message = "מספר הקלפי, מייל הוועדה או הסיסמה אינם נכונים." });
        }
        await HttpContext.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, AccountCookies.Principal(account),
            new AuthenticationProperties { IsPersistent = false });
        await audit.WriteAsync(new(AuditActions.Login, AuditResults.Success, account.Role, account.Identifier,
            "Account", account.Identifier, "התחברות בוצעה בהצלחה", HttpContext.TraceIdentifier), token);
        return Ok(new { account.Identifier, account.Role, account.KalpiId });
    }

    [Authorize]
    [HttpGet("me")]
    public IActionResult Me() => Ok(new {
        identifier = User.FindFirstValue(ClaimTypes.NameIdentifier), role = User.FindFirstValue(ClaimTypes.Role),
        kalpiId = User.FindFirstValue("KalpiId") is string id ? (int?)int.Parse(id) : null
    });

    [Authorize]
    [HttpPost("logout")]
    public async Task<IActionResult> Logout()
    {
        await HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
        return Ok(new { message = "יצאת מהמערכת." });
    }

}
