namespace KalpiTech.Api.Models;

// Internal lookup result. Only identifying details of an eligible voter reach the UI.
public sealed record Voter(string Id, int KalpiId, string FirstName, string LastName, bool Voted);
