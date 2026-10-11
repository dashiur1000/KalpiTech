using System.Globalization;

namespace KalpiTech.Api.Services;

public static class IsraelTime
{
    private static readonly TimeZoneInfo Zone = TimeZoneInfo.FindSystemTimeZoneById("Asia/Jerusalem");

    public static bool TryParse(string? text, out DateTime utc)
    {
        utc = default;
        if (!DateTime.TryParseExact(text, "yyyy-MM-dd'T'HH:mm", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var local)) return false;
        // DST gaps and repeated hours cannot identify a unique instant.
        if (Zone.IsInvalidTime(local) || Zone.IsAmbiguousTime(local)) return false;
        utc = TimeZoneInfo.ConvertTimeToUtc(local, Zone);
        return utc <= DateTime.MaxValue.AddHours(-36);
    }

    public static string? Format(DateTime? utc) => utc is { } value
        ? TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(value, DateTimeKind.Utc), Zone)
            .ToString("yyyy-MM-dd'T'HH:mm", CultureInfo.InvariantCulture) : null;
}
