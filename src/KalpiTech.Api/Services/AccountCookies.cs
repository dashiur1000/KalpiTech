using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using KalpiTech.Api.Data;
using KalpiTech.Api.Models;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;

namespace KalpiTech.Api.Services;

public sealed class AccountCookies(AccountStore accounts) : CookieAuthenticationEvents
{
    private static string Fingerprint(LoginAccount account) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(account.PasswordHash)));

    public static ClaimsPrincipal Principal(LoginAccount account)
    {
        var claims = new List<Claim> {
            new(ClaimTypes.NameIdentifier, account.Identifier), new(ClaimTypes.Name, account.Identifier),
            new(ClaimTypes.Role, account.Role), new("passwordVersion", Fingerprint(account))
        };
        if (account.KalpiId is int id) claims.Add(new("KalpiId", id.ToString(System.Globalization.CultureInfo.InvariantCulture)));
        return new(new ClaimsIdentity(claims, CookieAuthenticationDefaults.AuthenticationScheme));
    }

    public override async Task ValidatePrincipal(CookieValidatePrincipalContext context)
    {
        var identifier = context.Principal?.FindFirstValue(ClaimTypes.NameIdentifier);
        var account = identifier is null ? null : await accounts.FindAsync(identifier, context.HttpContext.RequestAborted);
        if (account is null || context.Principal?.FindFirstValue("passwordVersion") != Fingerprint(account)
            || context.Principal.FindFirstValue(ClaimTypes.Role) != account.Role)
        {
            context.RejectPrincipal();
            await context.HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
        }
    }

    public override Task RedirectToLogin(RedirectContext<CookieAuthenticationOptions> context)
    {
        context.Response.StatusCode = 401;
        return context.Response.WriteAsJsonAsync(new { message = "יש להתחבר למערכת." });
    }

    public override Task RedirectToAccessDenied(RedirectContext<CookieAuthenticationOptions> context)
    {
        context.Response.StatusCode = 403;
        return context.Response.WriteAsJsonAsync(new { message = "אין לך הרשאה לבצע פעולה זו." });
    }
}
