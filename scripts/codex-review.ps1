# Codex review in one step (Windows PowerShell), from a clone of this repo:
#     .\scripts\codex-review.ps1
# Pulls the latest main, runs Codex read-only on docs/REVIEW_REQUEST.md, and
# saves the answer to codex-review-output.txt (ignored by git) so it can be
# attached in the chat with Claude.

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
git pull --ff-only
$out = Join-Path (Get-Location) 'codex-review-output.txt'
codex exec --sandbox read-only "Read docs/REVIEW_REQUEST.md and do exactly what it says. Report findings only." 2>&1 | Tee-Object -FilePath $out
Write-Host ""
Write-Host "Saved to $out. Attach that file in the chat with Claude."
