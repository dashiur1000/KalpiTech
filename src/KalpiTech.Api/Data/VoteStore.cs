using KalpiTech.Api.Models;
using MySqlConnector;

namespace KalpiTech.Api.Data;

public sealed class VoteStore(DatabaseConnectionFactory connections, TimeProvider clock, AuditLogStore audit)
{
    public Task<VoteResult> ConfirmAsync(string id, int connectedKalpi, bool regular,
        string actorRole, string actorIdentifier, string correlationId, CancellationToken token)
        => ConfirmVoteAsync(id, connectedKalpi, regular, false, actorRole, actorIdentifier, correlationId, token);

    public Task<VoteResult> ConfirmEnvelopeAsync(string id, string actorIdentifier,
        string correlationId, CancellationToken token)
        => ConfirmVoteAsync(id, 0, false, true, "Admin", actorIdentifier, correlationId, token);

    // Both workflows share the same locks and conditional UPDATE, so they cannot double-register a voter.
    private async Task<VoteResult> ConfirmVoteAsync(string id, int connectedKalpi, bool regular, bool envelope,
        string actorRole, string actorIdentifier, string correlationId, CancellationToken token)
    {
        var action = envelope ? AuditActions.DoubleEnvelope : AuditActions.VoteConfirmation;
        var typeDetails = envelope ? "VotedIn=0 — ועדת הבחירות" :
            actorRole == "Accessible" ? "הצבעה בקלפי נגישה" : "הצבעה בקלפי רגילה";
        try
        {
            await using var connection = connections.Create();
            await connection.OpenAsync(token);
            await using var transaction = await connection.BeginTransactionAsync(token);
            // Same first lock as schedule edits and Python imports: never mix an import and a vote.
            var schedule = await ElectionStore.ReadRowAsync(connection, transaction, token);
            var found = false;
            var assignedKalpi = 0;
            var voted = false;
            VoteRecipient? recipient = null;
            await using (var read = new MySqlCommand(
                "SELECT KalpiId,Voted,FirstName,LastName,EmailAddress FROM People WHERE Id=@id FOR UPDATE", connection, transaction))
            {
                read.Parameters.AddWithValue("@id", id);
                await using var reader = await read.ExecuteReaderAsync(token);
                found = await reader.ReadAsync(token);
                if (found)
                {
                    assignedKalpi = reader.GetInt32(0);
                    voted = reader.GetBoolean(1);
                    recipient = new(reader.GetString(2), reader.GetString(3), reader.IsDBNull(4) ? null : reader.GetString(4));
                }
            }
            // The reader must be disposed before another command uses the same MySQL connection.
            if (!found)
                return await BlockedAsync(VoteStatus.NotFound, "מספר זהות אינו קיים", connection, transaction);
            var now = clock.GetUtcNow().UtcDateTime;
            if (envelope && !schedule.InCommitteeWindow(now))
                return await BlockedAsync(VoteStatus.CommitteeWindowClosed, "מחוץ לחלון 36 השעות", connection, transaction);
            if (!envelope && schedule.State(now) != "Active")
                return await BlockedAsync(VoteStatus.NotActive, "הבחירות אינן פעילות", connection, transaction);
            if (regular && assignedKalpi != connectedKalpi)
                return await BlockedAsync(VoteStatus.WrongKalpi, "הבוחר משויך לקלפי אחרת", connection, transaction);
            if (voted) return await BlockedAsync(VoteStatus.AlreadyVoted, "ניסיון הצבעה כפולה", connection, transaction);

            if (envelope)
            {
                // The internal committee location is created only for a successful envelope registration.
                await using var committee = new MySqlCommand(
                    "INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address,PasswordHash) " +
                    "VALUES (0,'Regular','','ועדת הבחירות המרכזית','',NULL) ON DUPLICATE KEY UPDATE KalpiId=KalpiId", connection, transaction);
                await committee.ExecuteNonQueryAsync(token);
            }

            await using var update = new MySqlCommand(
                "UPDATE People SET Voted=TRUE,VotedAt=@now,VotedIn=@kalpi " +
                "WHERE Id=@id AND Voted=FALSE" + (regular ? " AND KalpiId=@kalpi" : ""), connection, transaction);
            update.Parameters.AddWithValue("@id", id);
            update.Parameters.AddWithValue("@now", now);
            update.Parameters.AddWithValue("@kalpi", connectedKalpi);
            if (await update.ExecuteNonQueryAsync(token) != 1)
                return await BlockedAsync(VoteStatus.AlreadyVoted, "ניסיון הצבעה כפולה", connection, transaction);
            await audit.WriteAsync(connection, transaction, Event(AuditResults.Success, typeDetails), token);
            // Vote and success audit become visible together, or neither becomes visible.
            await transaction.CommitAsync(token);
            return new(VoteStatus.Saved, now, recipient);

            async Task<VoteResult> BlockedAsync(VoteStatus status, string details,
                MySqlConnection currentConnection, MySqlTransaction currentTransaction)
            {
                await audit.WriteAsync(currentConnection, currentTransaction, Event(AuditResults.Blocked, details), token);
                await currentTransaction.CommitAsync(token);
                return new(status);
            }
        }
        catch (Exception error) when (error is MySqlException or TimeoutException)
        {
            await audit.TryWriteAsync(Event(AuditResults.Failed, "כשל במסד הנתונים או בטרנזקציה"));
            throw;
        }

        AuditEvent Event(string result, string details) => new(action, result, actorRole, actorIdentifier,
            "Voter", id, details, correlationId);
    }
}
