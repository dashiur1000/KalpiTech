namespace KalpiTech.Api.Models;

public enum VoteStatus { Saved, NotActive, NotFound, WrongKalpi, AlreadyVoted, CommitteeWindowClosed }
public sealed record VoteRecipient(string FirstName, string LastName, string? EmailAddress);
public sealed record VoteResult(VoteStatus Status, DateTime? VotedAt = null, VoteRecipient? Recipient = null);
