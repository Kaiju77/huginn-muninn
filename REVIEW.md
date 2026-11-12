# Review log

## 2026-11-12: review round 11 (Fable 5.2; 438 tests ran, all OK)

The reviewer verified the core numbers as clean: no look-ahead or double counting in `study.py`, `calibration.py`, `daily_report.py` or `predictions.score`, and no data loss in the workflows.

1. P1: the round 10 fix for finding 3 skipped an episode once the event itself had rows. The krone is published before oil, so oil and gas would never have been logged. Now an episode is skipped only if a *different* event of it is logged.
2. P2: many small imprecise UCDP rows, judged one by one, never blocked a "calm" onset. Imprecise rows are spread over their range and added to the precise deaths; the calm check uses the combined window sums.
3. and 4. P2: labour, sport, price and business vetoes still dropped real strikes. Following the recall-first principle, the sport veto is removed, and only phrases that cannot describe an attack still veto ("strikes $20bn LNG deal", "go on strike", "strikes gold", "price rockets" unless followed by fired/hit/launched, "charm offensive"). Football false alarms are accepted.
5. and 6. P2/P3: same-story detection was either too loose (one shared round-up link) or too strict (a rejected story revived). Same story now means 2 or more shared links, or the only link of a single-link row.
7. P3: a late EIA batch dropped a horizon with no trace. It is now a visible void row.

Regression tests: `tests/test_review_round11.py`. Earlier tests were updated where round 11 deliberately changed behaviour.

## 2026-11-12: review round 10 (Fable 5.2; 425 tests ran, all OK; 6 of 11 round-9 fixes held)

**Principle adopted for the keyword screen:** prefer a false alarm (Kai ignores it with one click) to a missed attack. Only clear labour, business, price and sport phrases veto an ambiguous word. The AI screen and Kai do the precise sorting. This ends the vocabulary back-and-forth of rounds 6-10.

1. P1: any imprecise UCDP row with 1 death blocked a war's onset. Only fuzzy rows whose deaths, spread over their range, could reach the threshold within one window block an onset.
2. P2: the ±2-day same-story match dropped different stories (a repeated headline days later; one shared round-up link). Across days, a story now only matches if most of its article links are shared; a title match counts only within the same slot.
3. P2: a crisis was predicted twice if its opener was approved after a follow-up. Episodes that already have rows in the log are skipped.
4. P2: the 10-day entry cap was close to EIA's lag and dropped oil and gas rows for good. The cap is 21 days, and the report explains the lag.
5. P2: sport phrases vetoed real strikes ("Israel strikes back at Iran", "Grand Prix track"). These were removed (recall first).
6. P2: the BACKFILL label went only to stdout, and a backfill could overwrite the live report. The label is now written in the file, and the live report path is refused.
7. P3: ceasefire-deal phrasing gaps, and some new false positives. "strike … deal" is now a business deal only when every word in between is a deal modifier ($20bn, LNG, supply, long-term…). Accepted false alarm: "Kuwait strikes over pay deal…".
8. P3: "Iraqi oil rockets: militia fires…" was read as a price move. "oil" was removed from the price-subject list ("oil price rockets" still matches via "price").
9. P3: a hand-edited `date_public` stopped candidate suggestions. Unreadable dates never match and no longer crash.
10. P3: fuzzy rows ending up to 6 days before the calm start were ignored. The check now reaches back one window.
11. P3: the report wording now says a crisis is logged once (its opener).

Regression tests: `tests/test_review_round10.py`.

## 2026-11-12: review round 9 (independent reviewer on Fable 5.2; 410 tests ran, all OK)

1. P1: `--today` in the past filled the live log with fake "live" predictions built on a hindsight catalog (Brier 0.136 vs 0.294). The live log now only moves forward in real time. A backfill needs `--backfill-to FILE`, can never write the live log, and its report is labelled BACKFILL.
2. P1: one crisis was predicted and scored several times (the Twelve-Day War and the US strikes share an episode). Only the event that opens its episode is predicted (`first_of_episodes`).
3. P2: rows were recorded when most of the outcome was already known (late first run or late approval). Not recorded if the entry close is more than 10 days old.
4. P2: "Israel strikes Gaza despite ceasefire deal" was vetoed as a business deal. Words like despite, after, amid, on and over between "strike" and "deal" now keep it an escalation.
5. P2: one story spanning midnight or the 12:00 cutoff became two candidates. Same-story detection now looks at this region within 2 days either side.
6. P2: urllib forwarded the UCDP token header on a redirect to any host. Redirects are refused.
7. P3: a truncated UCDP response crashed with a traceback. `IncompleteRead`/`HTTPException` now give a clean, retried error.
8. P3: a damaged prediction log failed silently behind `|| true`. The failure is now flagged, and the run turns red after committing everything else.
9. P3: "strikes twice", "strikes gold" and "oil price rockets" passed. These are handled as sport or price phrases; "rockets fired at Israel" still counts.
10. P3: the 1989 truncation was 6 days short. The first allowed onset is `data_start + calm + window - 1`.
11. P3: imprecise GED rows were dropped before the calm check, so a noisy month looked calm. Imprecise rows with deaths now block a "calm" onset. Generated rows are `source_checked=no`.

Regression tests: `tests/test_review_round9.py`. The builders' tests were updated where behaviour changed on purpose.

## 2026-11-12: review round 8 (independent reviewer agent; 349 tests ran, all OK)

Three of the round 7 fixes held. Round 8 found new problems in the rest, and the fix is simpler rather than more patches:

1. P2: ids were duplicated when an AI candidate replaced a suffixed rejected row. The replacement now keeps that row's own id, and suffixes take the next free number.
2. P2: one story became several candidates across the morning and backup runs (new earliest headline, AI re-title, order flip). Candidates now store all supporting article URLs (`urls` column), and "same story" means a shared URL or the same title.
3. P2: splitting a region into stories by wording split single events (wire services word them differently). **Decision:** the keyword screen gives one candidate per region and day, and the AI screen separates events. Splitting by wording is removed.
4. P2: business deals ("Qatar strikes $20bn LNG supply deal") passed as escalations. Up to four words may now sit between "strike" and "deal". "Israel strikes Gaza as unions call general strike" counts, because only ambiguous words that sit inside a labour or business phrase are vetoed.
5. P3: the 19:00 UTC cutoff was 30 minutes late in summer for Brent, and wrong for the USD/NOK fixing (14:15 CET). **Decision:** the cutoff is now 12:00 UTC, which is safe for all four assets. It is conservative and can miss part of a first-day reaction, but it never peeks ahead.
6. P3: sport verbs ("striker rockets…") bypassed the sport veto. "rockets", "drones" and "missiles" were removed from the casualty override.
7. P3: the backtest caveat counts were hardcoded. They are now computed.

Also, from the reviewer's notes: `write_candidates` is now atomic.

Regression tests: `tests/test_review_round8.py`. Round 7 tests were updated where round 8 deliberately changed behaviour.

## 2026-11-12: review round 7 (independent reviewer agent; 340 tests ran, all OK)

1. P1: the round 6 date fix overcorrected. News first seen in the evening was dated that same day, so the `after_news` entry was a close printed before the news. For example, the 2025-06-12 22:00 UTC strike on Iran showed +13.5% at 5 days instead of +3.6%. News first seen at or after 19:00 UTC (around the Brent close) is now dated the next day.
2. P1: overlapping fetch windows could give a new story an existing id, and it was dropped silently. Same slot plus same story (same URL or title) is skipped; a different story gets a suffix (`-2`), and approval carries the suffix into the `event_id`.
3. P1/P2: an approval pushed during the daily run made its rebase fail, and the day's data was lost. The daily commit now saves what it fetched, resets to `main`, rebuilds candidates, the brief and the backtest on top, and retries up to 3 times.
4. P2: one-candidate-per-story hid a second story in the same region. A region is split into stories by shared headline words, but only when every part independently has 3 or more sites.
5. P2: the backtest understated noise. It now shows a 95% bootstrap interval for the Brier difference, the baseline's side-right count, the 12-comparisons caveat and the hindsight-curated-events caveat.
6. P3: vocabulary. Added "shells" (but not "Shell"). The sport veto is lifted when casualty words appear. Labour and business vetoes only match phrases next to "strike", and "struck a deal" is handled.
7. P3: `--date 20261111` wrote a malformed row. It must now be YYYY-MM-DD.
8. P3: the episode hint was rendered with mangled quotes. Fixed.

Regression tests: `tests/test_review_round7.py`.

## 2026-11-12: review round 6 (independent reviewer agent; 317 tests ran, all OK)

From now on, reviews are done by an independent reviewer agent in the cloud workspace: fresh context, all tests run, no temp-dir limits.

1. P1: a candidate was dated by the fetch day, not the first report, so the first day's reaction was lost. Candidates are now dated by their earliest `seendate`, the brief lists candidates from today and yesterday, and approval takes an optional `--date`.
2. P1: weekends were never screened (weekday cron with a 24-hour news window). The workflow now runs every day.
3. P2: the sport filter matched "League", "team" and "match" in real news, and one such headline sank a whole AI event. The filter now uses sport-only words, and sport headlines are dropped from support instead of rejecting the event.
4. P2: the keyword list missed "struck", "shelling" and "raid", and raised false alarms on labour strikes, "strikes deal" and "charm offensive". These are added or handled.
5. P2: a rejected candidate came back when the earliest headline changed. Only an AI candidate replaces a rejected keyword one.
6. P2: approvals shared a concurrency group and could be cancelled silently. The group is removed; the approval retries up to 3 times if `main` moved.
7. P2: one story naming two regions became two candidates. Regions whose articles were mostly used already are skipped.
8. P3: a hand-made event with the same id was treated as a resumed approval. This is now an error.
9. P3: candidate and note titles could inject markdown links. They are escaped.
10. P3: "24 hours" wording was wrong (the window is 36h), and a `fetched_at` without a zone crashed. Both fixed, and the suggest step is `continue-on-error`.

Regression tests: `tests/test_review_round6.py`.

## 2026-11-12: Codex review round 5 (event screen, AI screen, approval)

1. P2: old or future articles could appear as today's headlines and candidates. `daily.in_window` now keeps only articles seen in the 36 hours before the fetch, everywhere (brief, keyword screen, AI screen).
2. P2: `{"articles":[null]}` or `[{}]` overwrote good news. `parse` now keeps only articles with a title and an http URL, and fails if none remain.
3. P2: the AI could attach a story to unrelated headlines or cite numbers that don't exist. Every cited number must exist, the region must appear in the cited headlines themselves, and 2 or more of those sites are required.
4. P2: an AI result that was entirely rejected suppressed the keyword screen. When the AI rejected anything, keyword candidates for uncovered regions are added.
5. P2: a curl timeout crashed the AI step and the whole job. `TimeoutExpired`/`OSError` are caught, `main` catches everything, and the step is `continue-on-error`.
6. P2: "attacking" and "Yemeni" were missing. Added, with other -ing forms.
7. P3: sport headlines ("football team launches offensive") became conflict candidates. They are now excluded, in both screens.
8. P2: Norwegian supply news was filtered out. Equinor, Johan Sverdrup, the North Sea and Norway are now relevant, and the GDELT query includes them.
9. P2: approval wasn't atomic. The catalog and candidate file are swapped in with `os.replace`, and a retry after a half-finished approval completes it.

Regression tests: `tests/test_codex_round5.py`, one class per finding.

## 2026-11-11: Codex review round 4 (daily brief)

1. P2: a past brief could show headlines from later. Headlines now appear only when they were fetched on the brief's own date.
2. P2: the quiet-day fallback named a future event. It now uses only events on or before the brief's date.
3. P2: a failed news refresh looked successful. A brief with no fetch from today now says "today's fetch failed or has not run" and shows no old headlines.
4. P2: an empty or malformed GDELT response became "no news" and overwrote the cache. `parse` now raises, so the old file is kept and the step is marked failed.

Regression tests: `CodexRound4Test` in `tests/test_daily_report.py`.

## 2026-11-11: Codex review round 3 (four assets, page, workflow)

1. P2: the page showed a baseline share without n and range. `report.base_rate_rows` now includes `baseline n` and `baseline range %`.
2. P2: a truncated response could overwrite good history. `validate` now rejects data that is stale (latest date over 21 days old), starts after the asset's `starts_by`, or would start later, end earlier or have under 99% of the rows already on disk.
3. P2: `| tee` hid a failing study (no pipefail). The study step now runs in bash with `set -o pipefail`, so a failure stops the job before the commit.

Regression tests: `CodexRound3Test` in `tests/test_prices_pipeline.py`. 261 tests OK. Codex couldn't check WTI, Henry Hub or USD/NOK data because the workflow hadn't run yet.

## 2026-11-11: Codex review round 2 (catalog and loader)

1. P2: Desert Fox began about 22:00 GMT on 16 Dec 1998, after the Brent close. `date_public` changed to 1998-12-17, with the UK Parliament research paper as the source.
2. P2: the Libya uprising was public on 16 Feb 2011 (Benghazi clashes); 17 Feb was the planned day of rage. Changed to 2011-02-16.
3. P2: the Kuwait invasion and Desert Storm are one crisis. Merged into episode `1990-gulf-war` (21 episodes now).
4. P2: malformed CSV rows (extra or missing field, unterminated quote) were accepted silently. Both loaders now parse strictly and check the field count.
5. P3: a UTF-8 BOM broke the header. Both loaders now read `utf-8-sig`.

Regression tests: `CodexRound2Test` in `tests/test_catalog.py` and `PriceCsvStrictnessTest` in `tests/test_brent_pipeline.py`. 243 tests OK.

## 2026-11-11: Codex review of `study.py` (commit b642be3)

All five findings were P2. Each is fixed and has a regression test in `CodexReviewRegressionTest` in `tests/test_study.py`.

1. The era baseline included windows starting after the era ended (the slice happened after invalid windows were dropped). Fixed: windows are filtered by start date before anything else.
2. The baseline line had no n, CI or range. Fixed: the baseline now prints n, rises, share, Wilson CI, median and range, or "too few windows".
3. `min_n` could be set below 8. Fixed: `ValueError`.
4. A horizon of 0, a negative or non-integer horizon, or an empty horizon list passed when there were no events. Fixed: validated up front.
5. NaN/inf prices reached the statistics. Fixed: `sorted_closes` and `summarize` reject non-finite values.

Also adopted: the baseline uses non-overlapping windows, because overlapping windows understate the uncertainty in a Wilson CI (Codex note).

Not a code issue: 107 errors and the failed HTTP check in Codex's run came from its read-only sandbox, which can't create temp directories. Outside the sandbox: 220 tests OK, e2e 12/12.


Independent review on 2026-10-11 approved NOTE-01. Reviewer `9f54c300-bce2-448f-bc4f-edc0ec9d0208` read the observed restatement, the hypothesis label, the citation gates, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 195 tests, 195 passed, exit code 0. This verdict covers notes on the entered book. It is not native acceptance, a recommendation, or a filing match. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved PRICE-01. Reviewer `205dc4e4-7f9f-48cc-a38e-8a79d0059c51` read the accept form, the refusal gates, the evidence loader, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 190 tests, 190 passed, exit code 0. This verdict covers one explicit accept of a stored observation as an entered price. It is not native acceptance, a recommendation, or a ledger rate change. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved VALUE-01. Reviewer `8e1b27f5-d9e5-48d4-afad-f638572be7c4` read the two-date split, the unavailable gates, the locked fee example, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 186 tests, 186 passed, exit code 0. This verdict covers the entered performance page. It is not native acceptance, a recommendation, or a brokerage connection. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved ONBOARD-02. Reviewer `7f37206a-eb44-4416-b904-0ac8267e14b3` read the entered prices, the valuation page, the zero-subtotal sentence, the cash-snapshot overlap, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. An earlier review, `27c4a0ad-95f3-4283-8c02-a883f06c35fd`, rejected the slice because a known NOK subtotal of zero did not show "Allocation is incomplete." That sentence is on the page after the repair. The parent sandbox discovered 178 tests, 178 passed, exit code 0. This verdict covers entered prices and valuation on a selected date. It is not native acceptance, a performance attribution, or a brokerage connection. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved ONBOARD-01. Reviewer `4290b454-c3f9-4657-aaa3-858d55e48ad3` read the entered book, the ISIN check, the activity mapping, the manual-balance rules, the synthetic separation, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 167 tests, 167 passed, exit code 0. This verdict covers the entered portfolio workflow. It is not native acceptance, a brokerage connection, or a valuation. The synthetic demo remains separate. The listening desk was not restarted.

Independent review on 2026-10-11 approved INGEST-11. Reviewer `03aa61c5-c3d3-44ef-9f33-332065d20934` read the missing-series count, the cache-count sentence, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 154 tests, 154 passed, exit code 0. This verdict covers those page notes. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. The cap remains 500.

Independent review on 2026-10-11 approved INGEST-10. Reviewer `8a53642d-f76a-4fcd-985c-3f1fd545f043` read the cache count, the cap constant, the series quality flags, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 153 tests, 153 passed, exit code 0. This verdict covers the cache count and the quality labels. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. The cap remains 500. This note does not approve INGEST-10.

Independent review on 2026-10-11 approved INGEST-09. Reviewer `1b77f2bb-714f-4adf-9e95-67699efad7cf` read the series due labels, the calendar-day sentence, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 151 tests, 151 passed, exit code 0. This verdict covers those page notes. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. This note does not approve INGEST-09.

Independent review on 2026-10-11 approved INGEST-08. Reviewer `05ef935a-e39b-4b92-990a-0807c762b6bc` read the USD/NOK gap, the inventory freshness labels, the unchanged freshness rule, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 150 tests, 150 passed, exit code 0. This verdict covers the labeled gap and the freshness labels. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-07. Reviewer `93b4999a-71c0-4cca-9ca6-522a66b33861` read the separate policy-rate and NOWA note, the allowlist section, the client constant, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 150 tests, 150 passed, exit code 0. This verdict covers those page notes. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-06. Reviewer `836d93f4-c13a-499b-879f-5a9daf50a79f` read the retrieval dates on the series inventory, the static six-series list, the refresh request order, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 146 tests, 146 passed, exit code 0. This verdict covers those page notes and the named request list. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-05. Reviewer `a3090eaf-710a-40ca-8a86-d26c3075a5c4` read the USD/NOK ledger section, the future-date sentence, the freshness rule, the evidence page, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 145 tests, 145 passed, exit code 0. This verdict covers the newest stored USD/NOK note beside 10.25 and the future-date sentence. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-04. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594` read the CPI sentence, the series inventory, the freshness rule, the evidence page, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 137 tests, 137 passed, exit code 0. This verdict covers the monthly CPI sentence and the stored-series inventory. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. Rendering of stored revisions already existed before this diff.

Independent review on 2026-10-11 approved INGEST-03. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5`. This checkout adds the NOWA chart, the two-source EUR/NOK difference, and the one Statistics Norway CPI cell. That work is not approved by this note.

INGEST-02 was independently reviewed on 2026-10-11. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff` read the refresh, the rate parsers, the revision merge, the due status, the policy chart, the fixtures, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 130 tests, 130 passed, exit code 0. This verdict covers the five-series manual refresh. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

INGEST-01 was independently reviewed on 2026-10-11. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30` read the ingest package, the evidence identity rule, the evidence page, the registry, the recorded HTTP fixtures, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch from a public host. The parent sandbox before that review discovered 123 tests, 123 passed, exit code 0. After the review, the evidence page was given a sentence that separates `live_retrieval` rows from `synthetic_fixture` rows, and the evidence-page test was pointed at an empty cache so a local refresh cannot change the fixture assertion. A later parent sandbox discovered 123 tests, 123 passed, exit code 0. This verdict covers the read-only ingestion layer. It is not a live-retrieval pass, a ledger change, or production financial readiness. The synthetic 10.25 fixture remains the ledger rate.

EVIDENCE-01 was independently reviewed on 2026-10-11. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120` read the evidence module, both fixtures, the tests, the evidence page, and the parent receipt. Verdict: approve. The parent sandbox discovered 104 tests, 104 passed, exit code 0. A later parent rerun after a wording clarification also discovered 104 tests, exit code 0. The reviewer did not rerun the suite. This verdict covers the offline evidence register only. Live fetch stays off. The recorded fixture is synthetic. The page is not a recommendation. It is not production financial readiness.

DESK-01 was independently reviewed on 2026-10-11. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958` read the performance replay, the allocation module, the desk, the fixture targets, the waveform script, the tests, and the parent receipt. Verdict: approve. The parent sandbox discovered 89 tests, 89 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the synthetic desk only. It is not production financial readiness. Speech recognition is not implemented. The allocation rows are arithmetic gaps, not recommendations.

HM-01, discoverable accounting tests and explicit incomplete valuation, was independently reviewed on 2026-10-10. Kai then accepted it as a reviewed implementation.

Reviewer task `77d339bf-8bdf-4aaf-bfe9-2147630b425f` read the accounting module, the discoverable tests, `docs/OFFLINE_FOUNDATION.md`, `PROJECT_STATE.md`, `NEXT.md`, the preserved candidate baseline, the canonical Huginn & Muninn handoff, and both unittest receipts. Verdict: approve.

The parent sandbox rerun used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the checkout copied into container scratch and the network disabled. `python -m unittest discover -s tests -v` ran 8 tests, all passed, exit code 0.

This verdict covers that bounded slice only. It does not complete the broader accounting foundation. Currency compatibility, as-of checks, per-holding provenance, conversion, and valuation, exposure, and analytical coverage remain unfinished. `complete=true` means every stored holding is a Decimal. Non-finite Decimal values still count as known. The branch is not integrated into the canonical repository, deployed, or financially activated.

The HM-01 walkthrough demonstrates that accepted slice. It does not extend the 2026-10-10 HM-01 approval to currency, as-of, provenance, conversion, or coverage.

HM-01-WALKTHROUGH was independently reviewed on 2026-10-10. Reviewer `0261868b-647f-4cf2-91bc-db9b8ea7e0e0` read the walkthrough, its tests, the accounting module, the status documents, the HM-02 proposal, the canonical handoff, and the baseline and parent receipts. Verdict: approve. The parent sandbox rerun discovered 13 tests, 13 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the demonstration only. It does not implement or approve HM-02.

HM-02 is implemented in this checkout at `a6c692fb9af18794c1acf7bd038847e8bd7d726a`. Independent review on 2026-10-10 approved it. Reviewer `ed959b8d-9104-4874-a4f1-e085511cdf02` read the snapshot, its tests, the unchanged accounting module, the status documents, and the parent receipt. Verdict: approve. The parent sandbox rerun discovered 26 tests, 26 passed, exit code 0. A later clean-tree rerun of that same commit also discovered 26 tests, 26 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the qualified snapshot only. It does not authorize conversion, transactions, forecasts, recommendations, or HM-03.

The accounting ledger in `src/huginn_muninn/ledger.py` was independently reviewed on 2026-10-10. Reviewer `6e908566-155a-4fbf-9755-3d40359c1995` read the ledger, its tests, the walkthrough, the unchanged HM-01 and HM-02 modules, and the parent receipt. Verdict: approve. The parent sandbox discovered 57 tests, 57 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the synthetic ledger only. It does not authorize tax lots, recommendations, forecasts, or a further phase. At that review, a repeated statement row kept the first amount. PROTOTYPE-01 later changes that behavior, and its own review is recorded separately.

PROTOTYPE-01 was independently reviewed on 2026-10-10. Reviewer `55bf7095-d00c-40fd-a475-d7d8b1b5932c` read the ledger changes, the prototype, the fixture, the tests, the decimal and local-prototype notes, and the parent receipt. Verdict: approve. The parent sandbox discovered 75 tests, 75 passed, exit code 0. A later parent rerun, after table cells were kept on one line, again discovered 75 tests, exit code 0. The reviewer did not rerun the suite. This verdict covers the synthetic paper ledger only. It is not production financial readiness. A rejected event id still cannot be reused. The pages do not accept a new price or FX rate; those stay in the fixture. There is no cost basis.

## Historical

The following sentence is the earlier review note. It is not the current HM-01 verdict.

All completed planning artifacts retained with hashes. A bounded synthetic-data offline accounting foundation contract is saved for review. Architecture and implementation remain unapproved.
