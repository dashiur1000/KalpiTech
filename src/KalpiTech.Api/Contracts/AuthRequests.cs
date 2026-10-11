using System.ComponentModel.DataAnnotations;

namespace KalpiTech.Api.Contracts;

public sealed record LoginRequest(
    [Required, StringLength(254)] string Identifier,
    [Required, StringLength(128)] string Password);
