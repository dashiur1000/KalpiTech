using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class VoteStore(DatabaseConnectionFactory connections, TimeProvider clock)
{
    public Task<VoteResult> ConfirmAsync(string id, int connectedKalpi, bool regular, CancellationToken token)
        => ConfirmVoteAsync(id, connectedKalpi, regular, false, token);

    public Task<VoteResult> ConfirmEnvelopeAsync(string id, CancellationToken token)
        => ConfirmVoteAsync(id, 0, false, true, token);

    // Both workflows share the same locks and conditional UPDATE, so they cannot double-register a voter.
    private async Task<VoteResult> ConfirmVoteAsync(string id, int connectedKalpi, bool regular, bool envelope, CancellationToken token)
    {
        await using var connection = connections.Create();
        await connection.OpenAsync(token);
        await using var transaction = await connection.BeginTransactionAsync(token);
        // Same first lock as schedule edits and Python imports: never mix an import and a vote.
        var schedule = await ElectionStore.ReadRowAsync(connection, transaction, token);
        int assignedKalpi;
        bool voted;
        VoteRecipient recipient;
        await using (var read = new MySqlCommand(
            "SELECT KalpiId,Voted,FirstName,LastName,EmailAddress FROM People WHERE Id=@id FOR UPDATE", connection, transaction))
        {
            read.Parameters.AddWithValue("@id", id);
            await using var reader = await read.ExecuteReaderAsync(token);
            if (!await reader.ReadAsync(token)) return new(VoteStatus.NotFound);
            assignedKalpi = reader.GetInt32(0);
            voted = reader.GetBoolean(1);
            recipient = new(reader.GetString(2), reader.GetString(3), reader.IsDBNull(4) ? null : reader.GetString(4));
        }
        if (envelope)
        {
            // Reserved location 0 represents the committee, displayed as 0000.
            // NULL password and login's positive-ID rule prevent station login as 0000.
            // Create it within this transaction, so an unsuccessful request cannot leave changes.
            await using var committee = new MySqlCommand(
                "INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address,PasswordHash) " +
                "VALUES (0,'Regular','','ועדת הבחירות המרכזית','',NULL) ON DUPLICATE KEY UPDATE KalpiId=KalpiId", connection, transaction);
            await committee.ExecuteNonQueryAsync(token);
        }
        // Check time AFTER acquiring all locks, including a possible wait for the voter/station row.
        var now = clock.GetUtcNow().UtcDateTime;
        if (envelope && !schedule.InCommitteeWindow(now)) return new(VoteStatus.CommitteeWindowClosed);
        if (!envelope && schedule.State(now) != "Active") return new(VoteStatus.NotActive);
        if (regular && assignedKalpi != connectedKalpi) return new(VoteStatus.WrongKalpi);
        if (voted) return new(VoteStatus.AlreadyVoted);

        await using var update = new MySqlCommand(
            "UPDATE People SET Voted=TRUE,VotedAt=@now,VotedIn=@kalpi " +
            "WHERE Id=@id AND Voted=FALSE" + (regular ? " AND KalpiId=@kalpi" : ""), connection, transaction);
        update.Parameters.AddWithValue("@id", id);
        update.Parameters.AddWithValue("@now", now);
        update.Parameters.AddWithValue("@kalpi", connectedKalpi);
        if (await update.ExecuteNonQueryAsync(token) != 1) return new(VoteStatus.AlreadyVoted);
        // Success must be returned only after COMMIT. Disposal rolls back every earlier exit.
        await transaction.CommitAsync(token);
        return new(VoteStatus.Saved, now, recipient);
    }
}
