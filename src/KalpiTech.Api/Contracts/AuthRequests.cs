using System.ComponentModel.DataAnnotations;

namespace KalpiTech.Api.Contracts;

public sealed record LoginRequest(
    [Required, StringLength(254)] string Identifier,
    [Required, StringLength(128)] string Password);

public sealed record ChangeAdminPasswordRequest(
    [Required, StringLength(128)] string CurrentPassword,
    [Required, StringLength(128, MinimumLength = 12)] string NewPassword);

public sealed record SetKalpiPasswordRequest(
    [Range(1, int.MaxValue)] int KalpiId,
    [Required, StringLength(128, MinimumLength = 12)] string NewPassword);
