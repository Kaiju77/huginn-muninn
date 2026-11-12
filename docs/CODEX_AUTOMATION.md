# Automatic Codex reviews (one-time setup on Kai's PC)

Claude writes `docs/REVIEW_REQUEST.md` and pushes. A scheduled task on Kai's PC
notices the change, runs Codex read-only, and saves the answer in the clone.
Claude reads it through the connected folder. No copy-paste per round.

## Setup (once, in PowerShell)

    cd C:\Users\kaiar\Documents\projects\hm-review
    git pull
    schtasks /Create /TN "Huginn-Muninn Codex review" /SC MINUTE /MO 20 /F /TR "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Users\kaiar\Documents\projects\hm-review\scripts\codex-review-watch.ps1"

Test it right away instead of waiting 20 minutes:

    schtasks /Run /TN "Huginn-Muninn Codex review"

## Files (ignored by git)

- `codex-review-output.txt`: Codex's answer to the latest request
- `codex-review-status.json`: which commit and request were reviewed, and when
- `codex-review.lock`: present while a review runs

## Stop it

    schtasks /Delete /TN "Huginn-Muninn Codex review" /F

It runs only while you are logged in, and only when the review request changed.
