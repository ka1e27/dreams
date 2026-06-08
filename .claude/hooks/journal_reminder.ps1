# Stop hook: remind Claude to record a session entry in docs/session_journal.md.
# Reads the hook payload (JSON) from stdin. Blocks the stop ONCE per session so
# Claude updates the journal; on the re-entrant stop (stop_hook_active = true) it
# allows the session to end, so there is no loop and at most one reminder.
$raw = [Console]::In.ReadToEnd()
try { $j = $raw | ConvertFrom-Json } catch { $j = $null }
if ($j -and $j.stop_hook_active) { exit 0 }

$payload = @{
    decision = "block"
    reason   = "Reminder (per CLAUDE.md): before ending this session, append a newest-first entry to docs/session_journal.md summarizing what you worked on. If you have already added an entry this session, just stop again."
} | ConvertTo-Json -Compress
Write-Output $payload
