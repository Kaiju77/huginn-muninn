# Runs a Codex review automatically when Claude has written a new review request.
# Meant for Windows Task Scheduler, every 20 minutes (see docs/CODEX_AUTOMATION.md).
#
# Each run: git pull; if docs/REVIEW_REQUEST.md changed since the last review,
# run Codex read-only on it and write
#   codex-review-output.txt  - Codex's answer
#   codex-review-status.json - which commit and request were reviewed, and when
# Both files are ignored by git. Claude reads them through the connected folder.

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$lock = Join-Path (Get-Location) 'codex-review.lock'
if (Test-Path $lock) {
    # A review is still running; an old lock (over 2 hours) is from a crash.
    if ((Get-Date) - (Get-Item $lock).LastWriteTime -lt [TimeSpan]::FromHours(2)) { exit 0 }
}
New-Item -ItemType File -Path $lock -Force | Out-Null
try {
    git pull --ff-only --quiet
    $request = Get-FileHash 'docs/REVIEW_REQUEST.md' -Algorithm SHA256
    $statusFile = Join-Path (Get-Location) 'codex-review-status.json'
    if (Test-Path $statusFile) {
        $last = Get-Content $statusFile -Raw | ConvertFrom-Json
        if ($last.request_sha256 -eq $request.Hash) { exit 0 }   # already reviewed
    }
    $commit = (git rev-parse HEAD).Trim()
    $out = Join-Path (Get-Location) 'codex-review-output.txt'
    $started = (Get-Date).ToUniversalTime().ToString('o')
    codex exec --sandbox read-only "Read docs/REVIEW_REQUEST.md and do exactly what it says. Report findings only." 2>&1 |
        Out-File -FilePath $out -Encoding utf8
    @{ commit = $commit; request_sha256 = $request.Hash; started_utc = $started;
       finished_utc = (Get-Date).ToUniversalTime().ToString('o') } |
        ConvertTo-Json | Out-File -FilePath $statusFile -Encoding utf8
}
finally {
    Remove-Item $lock -ErrorAction SilentlyContinue
}
