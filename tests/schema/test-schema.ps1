# Integration tests run against a uniquely named disposable database, not VotesDb.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$invokeSql = Join-Path $projectRoot 'scripts/invoke-sql.ps1'
$schemaFile = Join-Path $projectRoot 'src/KalpiTech.Api/Data/Sql/001_initial_schema.sql'
$testDatabase = 'KalpiTechTest_' + [Guid]::NewGuid().ToString('N')
$created = $false
$passed = 0

function Run-Sql([string]$sql) {
    & $invokeSql -UseRoot -Database $testDatabase -Query $sql
}
function Assert-Sql([string]$name, [string]$sql) {
    $result = @(Run-Sql $sql)
    if ($result[-1] -ne '1') { throw "FAIL: $name. Result: $result" }
    $script:passed++
    Write-Host "PASS: $name"
}
function Assert-Rejected([string]$name, [string]$sql, [int]$code) {
    try { Run-Sql $sql | Out-Null }
    catch {
        if ($_.Exception.Message -notmatch "ERROR $code ") { throw }
        $script:passed++
        Write-Host "PASS: $name"
        return
    }
    throw "FAIL: $name was accepted."
}

Push-Location $projectRoot
try {
    & $invokeSql -UseRoot -Query "CREATE DATABASE $testDatabase CHARACTER SET utf8mb4;" | Out-Null
    $created = $true
    & $invokeSql -UseRoot -Database $testDatabase -File $schemaFile | Out-Null
    Assert-Sql 'Initial election schedule is unset' 'SELECT COUNT(*) = 1 FROM ElectionSettings WHERE Id=1 AND StartsAt IS NULL AND EndsAt IS NULL AND LoadLockedUntil IS NULL;'
    Run-Sql (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fixtures.sql') -Raw -Encoding UTF8) | Out-Null
    Assert-Sql 'Defaults and leading zeros' "SELECT COUNT(*) = 1 FROM People WHERE Id='001234567' AND Voted=FALSE AND EmailAddress IS NULL AND VotedAt IS NULL AND VotedIn IS NULL;"
    Assert-Sql 'Hebrew round trip' (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'assert-hebrew.sql') -Raw -Encoding UTF8)
    Assert-Rejected 'Duplicate identity' "INSERT INTO People (Id,KalpiId,FirstName,LastName) VALUES ('001234567',1,'a','b');" 1062
    Assert-Rejected 'Duplicate polling station' "INSERT INTO Kalpi (KalpiId,KalpiType,City,Place,Address) VALUES (1,'Regular','a','b','c');" 1062
    Assert-Rejected 'Missing assigned polling station' "INSERT INTO People (Id,KalpiId,FirstName,LastName) VALUES ('123456789',99,'a','b');" 1452
    Assert-Rejected 'Invalid identity length' "INSERT INTO People (Id,KalpiId,FirstName,LastName) VALUES ('12345678',1,'a','b');" 3819
    Assert-Rejected 'Non-digit identity' "INSERT INTO People (Id,KalpiId,FirstName,LastName) VALUES ('12345678a',1,'a','b');" 3819
    Assert-Rejected 'Invalid polling station type' "UPDATE Kalpi SET KalpiType='Other' WHERE KalpiId=1;" 3819
    Assert-Rejected 'Partial vote registration' "UPDATE People SET Voted=TRUE WHERE Id='001234567';" 3819
    Assert-Rejected 'Invalid Boolean value' "UPDATE People SET Voted=2 WHERE Id='001234567';" 3819
    Assert-Rejected 'Missing actual polling station' "UPDATE People SET Voted=TRUE,VotedAt='2026-10-10 12:00:00',VotedIn=99 WHERE Id='001234567';" 1452
    Assert-Rejected 'Delete referenced assigned station' 'DELETE FROM Kalpi WHERE KalpiId=1;' 1451
    Run-Sql "UPDATE People SET Voted=TRUE,VotedAt='2026-10-10 12:00:00',VotedIn=2 WHERE Id='001234567'; UPDATE ElectionSettings SET StartsAt='2026-10-10 06:00:00',EndsAt='2026-10-10 19:00:00' WHERE Id=1;" | Out-Null
    Assert-Sql 'Actual station differs from assigned station' "SELECT COUNT(*) = 1 FROM People WHERE Id='001234567' AND KalpiId=1 AND VotedIn=2 AND Voted=TRUE;"
    Assert-Rejected 'Delete referenced actual station' 'DELETE FROM Kalpi WHERE KalpiId=2;' 1451
    Assert-Sql '36 hour deadline' "SELECT COUNT(*) = 1 FROM ElectionSettings WHERE LoadLockedUntil='2026-10-11 18:00:00';"
    Assert-Rejected 'Election must end after it starts' "UPDATE ElectionSettings SET EndsAt=StartsAt WHERE Id=1;" 3819
    Assert-Rejected 'Partial election schedule' 'UPDATE ElectionSettings SET EndsAt=NULL WHERE Id=1;' 3819
    Assert-Rejected 'Only one election settings row' 'INSERT INTO ElectionSettings (Id) VALUES (2);' 3819
    Run-Sql "START TRANSACTION; INSERT INTO People (Id,KalpiId,FirstName,LastName) VALUES ('987654321',1,'a','b'); ROLLBACK;" | Out-Null
    Assert-Sql 'Rollback preserves original data' 'SELECT COUNT(*) = 1 FROM People;'
    & $invokeSql -UseRoot -Database $testDatabase -File $schemaFile | Out-Null
    Assert-Sql 'Reapplying schema preserves votes and schedule' "SELECT (SELECT COUNT(*) FROM People WHERE Voted=TRUE)=1 AND (SELECT StartsAt FROM ElectionSettings WHERE Id=1)='2026-10-10 06:00:00';"

    # Restart only this project's MySQL container. Its volume must retain committed rows.
    docker compose restart mysql
    if ($LASTEXITCODE -ne 0) { throw 'MySQL restart failed.' }
    docker compose up -d --wait --wait-timeout 60 mysql
    if ($LASTEXITCODE -ne 0) { throw 'MySQL did not become healthy after restart.' }
    Assert-Sql 'Votes and UTC schedule survive restart' "SELECT (SELECT COUNT(*) FROM People WHERE Id='001234567' AND Voted=TRUE AND VotedAt='2026-10-10 12:00:00' AND VotedIn=2)=1 AND (SELECT COUNT(*) FROM ElectionSettings WHERE StartsAt='2026-10-10 06:00:00' AND EndsAt='2026-10-10 19:00:00' AND LoadLockedUntil='2026-10-11 18:00:00')=1;"
    Write-Host "All $passed schema checks passed."
}
finally {
    if ($created) {
        # Exact database created by this invocation, never the application database.
        & $invokeSql -UseRoot -Query "DROP DATABASE $testDatabase;" | Out-Null
    }
    Pop-Location
}
