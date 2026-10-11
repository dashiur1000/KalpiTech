using System.Net.Mail;
using System.Net.Http.Json;
using KalpiTech.Api.Models;

namespace KalpiTech.Api.Services;

// One attempt after COMMIT. No queue, retries, recipient logging or changes to the vote.
public sealed class VoteConfirmationEmail(HttpClient client, IConfiguration configuration, ILogger<VoteConfirmationEmail> logger)
{
    public static void ValidateConfiguration(IConfiguration configuration)
    {
        if (!configuration.GetValue<bool>("Mail:Enabled")) return;
        var key = configuration["Mail:ApiKey"];
        if (string.IsNullOrWhiteSpace(key) || key.Any(char.IsControl) || !ValidAddress(configuration["Mail:SenderEmail"]))
            throw new InvalidOperationException("Enabled email requires Mail:ApiKey and a valid verified Mail:SenderEmail.");
    }

    private static bool ValidAddress(string? value) => !string.IsNullOrWhiteSpace(value)
        && !value.Any(char.IsControl) && MailAddress.TryCreate(value, out var address) && address.Address == value;

    public async Task SendAsync(VoteResult result)
    {
        if (result.Status != VoteStatus.Saved || result.Recipient is not { } recipient
            || !configuration.GetValue<bool>("Mail:Enabled") || !ValidAddress(recipient.EmailAddress)) return;
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, "smtp/email");
            request.Headers.Add("api-key", configuration["Mail:ApiKey"]);
            request.Content = JsonContent.Create(new {
                sender = new { email = configuration["Mail:SenderEmail"], name = configuration["Mail:SenderName"] ?? "ועדת הבחירות" },
                to = new[] { new { email = recipient.EmailAddress, name = $"{recipient.FirstName} {recipient.LastName}" } },
                subject = "וועדת הבחירות המרכזית - אישור הצבעה",
                textContent = $"שלום {recipient.FirstName} {recipient.LastName}, הצבעתך נקלטה בהצלחה!"
            });
            // A disconnected browser must not cancel the attempt after a committed vote.
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, CancellationToken.None);
            if (!response.IsSuccessStatusCode) logger.LogWarning("Confirmation email failed. HTTP status: {Status}.", (int)response.StatusCode);
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException)
        {
            // Exception text/provider responses may contain personal data: log only its type.
            logger.LogWarning("Confirmation email failed ({ExceptionType}); the vote remains saved.", error.GetType().Name);
        }
    }
}
