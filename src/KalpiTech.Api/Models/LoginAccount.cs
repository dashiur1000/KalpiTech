namespace KalpiTech.Api.Models;

// PasswordHash is internal and is never serialized as an API response.
public sealed record LoginAccount(string Identifier, string Role, int? KalpiId, string PasswordHash);
