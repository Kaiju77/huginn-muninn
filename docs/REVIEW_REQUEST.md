# Review request for Codex, round 6 (2026-11-12)

Rounds 1-5 are logged in `REVIEW.md`. Review the commits after `0119cf5`:

- Groq provider: `scripts/ai_screen.py` (`providers`, `groq_call`, `screen_all`)
- Round 5 fixes: `src/huginn_muninn/daily.py` (`in_window`, `relevant`), `src/huginn_muninn/candidates.py`, `src/huginn_muninn/ai_screen.py`, `scripts/fetch_news.py`, `scripts/suggest_events.py`, `scripts/approve_event.py`
- Tests: `tests/test_codex_round5.py`, `tests/test_ai_screen.py`

Run (some tests need temp dirs, which the read-only sandbox doesn't have; list those as not run, not as failures):

    python -m unittest tests.test_codex_round5 tests.test_ai_screen -v

Check, and report each finding with file:line, severity and a failing example:

- **Round 5.** Is each of the 9 findings really closed? Try a variant of each failing example.
- **Groq.** Is the key ever exposed (command line, logs, status file, exceptions)? Is the fallback order right if the Groq key is missing, invalid, or rate-limited (429)?
- **Window.** Is 36 hours plus 1 hour of slack a sensible window given GDELT's seendate in UTC? Edge cases around midnight UTC.
- **Atomic approval.** Any remaining sequence that leaves the catalog and the candidate file out of step?

Report only. Don't edit files.
