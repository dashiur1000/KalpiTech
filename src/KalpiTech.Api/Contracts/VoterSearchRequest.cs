namespace KalpiTech.Api.Contracts;

// Validation is explicit in the controller to return a specific Hebrew ID message.
public sealed record VoterSearchRequest(string? Id);
