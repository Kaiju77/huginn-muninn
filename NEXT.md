# Next Steps

Branch `claude/event-study-plan` (from `claude/e2e-portfolio`), 2026-11-11.

Done: product redefined as event study and historical base rates. `PROJECT_STATE.md`, `ROADMAP.md` and `CLAUDE.md` rewritten. The old ledger docs are in `docs/archive/`.

1. Kai: get a free EIA API key (https://www.eia.gov/opendata/) and store it as the environment variable `EIA_API_KEY`. Don't commit it.
2. Done: `data/events/mideast-conflict.csv` (28 events, 22 episodes, 1988-2026), loader `catalog.py` with validation, 5 tests. Kai: review the list; 15 links are still `source_checked=no`.
3. Done: `src/huginn_muninn/study.py` with synthetic tests (Wilson CI, no look-ahead entry, skip rather than truncate, era filter, baseline). Full suite: 212 tests OK.
4. Done: Codex review, 5 findings fixed (see `REVIEW.md`). 24 study tests, 220 total.
5. Done: entry rule, `after_news` default.
6. Done 2026-11-11: repo pushed to github.com/Kaiju77/huginn-muninn (`main`). Workflows: `tests` (every push) and `fetch-brent` (weekdays 06:23 UTC, plus manual runs).
7. Done: first `fetch-brent` run, 10,013 daily rows from 1987-05-20 to 2026-11-03. First real result: conflicts tend to see a jump at the news (`before_news`, 5 days: 17/22 rose), then Brent drifts down (`after_news`, 20 days: 7/22 rose vs baseline 53%). n=22, so the intervals are wide.
7b. Done: Codex review round 2, 5 findings fixed (see `REVIEW.md`). With 21 episodes the pattern holds: a jump on the news, then a fade.
8. Then: Streamlit page (v1 step 4).

No merge, push or deploy without Kai's OK. Kai approved the initial push of `main` on 2026-11-11.

## Historical


Branch `claude/e2e-portfolio` (from `cursor/hm-01` @ 67df1fc), 2026-11-11.

Done: `scripts/e2e_portfolio.py` and `tests/test_e2e_portfolio.py` drive the entered-portfolio workflow over HTTP with synthetic data (12/12 steps). Full suite: 196 tests OK. See `docs/E2E_PORTFOLIO.md`.

1. Kai: run `python scripts/e2e_portfolio.py` on Windows and confirm 12/12 steps pass.
2. Decide whether the e2e script should also cover `POST /portfolio/price` (accept a stored observation) and the USD-cash path (attribution unavailable).
3. Settle the product brief: this repo is the finance system. The Claude project brief (multi-agent daily briefing) does not match it.
4. Still open from the handoff: no pyproject or CI, master is not integrated, and EDGAR is blocked on a contact string.

No merge, push, or deploy has been done.

## Historical

The following pointer was current before 2026-11-11. It is not the current next step.


Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. NOTE-01 is reviewed at `2052cf59a9636558732ef71410e31b0802277a28`. Reviewer `9f54c300-bce2-448f-bc4f-edc0ec9d0208` approved notes that restate a stored observation and keep a hypothesis labeled. The next executable task is item 2.
2. Leave EDGAR, FRED, news feeds, market-data vendors, and brokerage connections in `HUMAN_TASKS.md`. Do not scrape. Do not fetch EDGAR without a real contact string. Do not fetch FRED.
3. A later slice can match a holding to a filing only after that contact string exists. Do not invent a filing.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`. The product path is `ROADMAP.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before ONBOARD-02. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. ONBOARD-01 is reviewed at `d27d8bf986d4d76c48cc2de31b4ed96c45e7dca9`. Reviewer `4290b454-c3f9-4657-aaa3-858d55e48ad3` approved the entered accounts, instruments, activities, and manual balances. The next executable task is item 2.
2. After it: value an entered holding as quantity times one supplied price on the valuation date, or show the manual balance on its as-of date. A missing price stays unknown. Do not invent a price. Do not convert currency in this task.
3. After that: separate contributions and withdrawals from the change in value between two dates when every required price and the holding path are known. If a manual balance is the only figure, say attribution is unavailable.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`. The product path is `ROADMAP.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before ONBOARD-01. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-11 is reviewed at `c4e57ffc790a2321dea2c28d2d5c15028dba293d`. Reviewer `03aa61c5-c3d3-44ef-9f33-332065d20934` approved the missing-series count and the sentence that the synthetic fixture is not part of the cache count. The next executable task is item 2.
2. When the cache count is greater than the cap, say the stored count is above the cap because the first batch can stay above 500. Use the existing trim rule. Do not change the cap. If the count is not above the cap, omit that sentence.
3. After that: keep three ready notes on the evidence page that do not fetch. State the number of stored conflicts. State the number of stored revisions. State whether the last refresh recorded an error. Each line is omitted when the count is zero or no error is stored.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-11. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-10 is reviewed at `9552b0b2a8e523b20430f6725e69e82cabd5df5c`. Reviewer `8a53642d-f76a-4fcd-985c-3f1fd545f043` approved the stored observation count beside the 500 cap and the quality flag of the newest stored row for each of the six series. The next executable task is item 2.
2. State how many of the six series are not stored. That count is computed from the same rows as the quality section. Include the exact sentence "A missing series is not a zero." Do not fetch.
3. State that the cache count does not include the synthetic fixture rows. Include the exact sentence "The synthetic fixture is not part of the cache count." Do not fetch.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-10. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-09 is reviewed at `177b1dbf5d651da11b7debdb5c5aebbad589b588`. Reviewer `1b77f2bb-714f-4adf-9e95-67699efad7cf` approved the due or current label beside each refresh series and the calendar-day sentence. The next executable task is item 2.
2. After it: on the evidence page, show the count of stored cache observations and the existing 500 cap. Say the cap drops the oldest observation dates that are absent from a new batch. Do not change the cap. Do not fetch.
3. After that: leave the human decisions in `HUMAN_TASKS.md` as the remaining gate. Do not implement EDGAR, FRED, another SSB table, a ledger write, or a scheduler. The ready code task that stays inside the evidence page is: name the quality flag of the newest stored row for each of the six series when that series has a stored row, and say the flag is a label. If a series has no stored row, say it is not stored.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-09. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-08 is reviewed at `ce01011006d46c91c7027b6cbb94385b887d0410`. Reviewer `05ef935a-e39b-4b92-990a-0807c762b6bc` approved the labeled USD/NOK gap and the freshness flags on the stored-series lines. The next executable task is item 2.
2. After it: beside the static six-series list, show the existing due or current label for the source that owns each series. Map Norges Bank USD/NOK, Norges Bank EUR/NOK, the policy rate, and NOWA to norges-bank-open-data. Map ECB NOK/EUR to ecb-sdw. Map the CPI cell to ssb-statbank. Use due_status. Do not fetch. A source with no fresh non-synthetic row stays due.
3. After that: on the evidence page, repeat the last stored refresh timestamp that is already in the cache, and say that a later calendar day is not a scheduled refresh. Do not add a scheduler.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-08. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-07 is reviewed at `a29e6ad0d562739f3823d7fde537c8f376b13db3`. Reviewer `93b4999a-71c0-4cca-9ca6-522a66b33861` approved the separate policy-rate and NOWA note and the allowlist hosts. The next executable task is item 2.
2. After it: for the newest stored USD/NOK observation, show stored value minus Decimal('10.25') as a labeled difference. Exact zero renders as 0. Include this exact sentence: "The USD/NOK gap is not a recommendation and is not copied into the ledger." Do not call add_rate. If no USD/NOK row is visible, omit the difference and keep the existing empty-state sentence.
3. After that: on each stored-series inventory line, state the freshness flag of the latest row against the selected page date, using the existing freshness_flags function. Do not change that function. A line with two rows on the latest date states both flags.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-07. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-06 is reviewed at `3fbb139ec9eae87a6cc797ac25db3910ed384ca8`. Reviewer `836d93f4-c13a-499b-879f-5a9daf50a79f` approved the retrieval dates on the stored-series inventory and the static six-series list. The next executable task is item 2.
2. After it: a read-only note that the policy rate and NOWA are different series. Show each latest stored value when that subject is visible. Do not add them, average them, or treat a shared percent unit as one rate. Say they are not combined.
3. After that: state the allowlist hosts on the evidence page as text taken from the existing client allowlist constant, still without opening a socket on GET.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-06. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-05 is reviewed at `ffdb4096b83fc9417a95a78f1b4833d7ad717732`. Reviewer `a3090eaf-710a-40ca-8a86-d26c3075a5c4` approved the newest USD/NOK note beside 10.25 and the future-date sentence. The next executable task is item 2.
2. After it: add the retrieval date of the latest row to each stored-series inventory line. Still computed from stored rows. No fetch and no scheduler.
3. After that: on the evidence page, name the six series a manual refresh requests, as a static list, without calling the network on GET. The list is USD/NOK, EUR/NOK, policy rate, NOWA, ECB NOK/EUR, and the one CPI cell.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-05. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-04 is reviewed at `41b7175e5f771934d10dd1921a60ee0b3f6e097d`. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594` approved the monthly CPI sentence and the stored-series inventory. Stored revisions were already rendered before that diff. The next executable task is item 2.
2. On the evidence page, place the newest stored USD/NOK observation beside the synthetic ledger rate 10.25. State the stored value, its observation date, its quality flag, and whether the two numbers are equal. Say that a match and a gap are both not a ledger update. Do not call `add_rate`.
3. After that: when a visible row is `future_observation` or `future_retrieval` against the selected date, say that the row is later than the selected date and was not dropped. Do not change the freshness rule.

Leave EDGAR, FRED, other SSB tables, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-04. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`.

1. INGEST-03 is reviewed at `fd11a8b358ed67fcd142620b9bdb5a71fa251821`. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5` approved the NOWA chart, the two-source EUR/NOK difference, and the one CPI cell. The next executable task is item 2.
2. After it: state on the evidence page that the CPI observation date is the first day of 2026M07, so a 7-day freshness window marks July stale in October. That staleness is the monthly publication, not a failed daily refresh.
3. After that: a stored-series inventory listing the latest observation date for each subject, still without a scheduler.
4. Leave EDGAR, FRED, vendors, and ledger acceptance in `HUMAN_TASKS.md`.

The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-03. It is not the current next step.

Ready work on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`. These tasks do not depend on the open human decisions in `HUMAN_TASKS.md`.

1. INGEST-02 is reviewed at `6b2e10e7d33eb762a2f9b2734729777475e8fe7d`. It adds Norges Bank EUR/NOK, the verified policy-rate key `IR/B.KPRA.SD.R`, and the NOWA rate to the explicit manual refresh, keeps revision records, caps stored observations at 500, prints connected sources as current or due, and draws stored policy-rate points. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff` approved it. The next executable task is item 2.
2. Show NOWA beside the policy rate with its own stored-point chart, still without a scheduler.
3. A read-only comparison on the evidence page between the Norges Bank EUR/NOK observation and the ECB NOK/EUR observation for the same date, labeled as two sources, with no recommendation and no ledger write.

Statistics Norway remains blocked on a current table id, so it stays under human decisions rather than in this ready queue. The synthetic ledger rate remains 10.25. The desk remains in research mode. See `docs/INGEST.md`.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this queue.

## Historical

The following pointer was current before INGEST-01. It is not the current next step.

EVIDENCE-01 is a reviewed local evidence register on branch `cursor/hm-01` at `1f6f26750c0b196aaea57d2f70c9edb2833628d7`. The baseline before the edits was `3079c1b69d19f9512691d4fb244f5cdf834b16a2`. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120` approved it. A further phase was not authorized by that review.

At EVIDENCE-01, live fetch stayed off. The evidence page read `fixtures/source_registry.json` and `fixtures/evidence_observations.json`. No source was connected. The desk remained in research mode. See `docs/EVIDENCE.md`. The recommended next phase, when separately approved, was a reviewed egress profile for one public source, still read-only, with recorded responses in tests. INGEST-01 is that later explicit increment. No recommendations follow from connecting a source.

The hosted FastAPI, React, and PostgreSQL target remains deferred. No merge, push, deployment, financial connection, or purchase follows from this implementation.

## Historical

The following pointer was current before EVIDENCE-01. It is not the current next step.

DESK-01 is a reviewed local night desk on branch `cursor/hm-01` at `83750c9c6ec98a48fd24c864ee2cea184a37cf15`. The baseline before the edits was `0ada7b5904d76920128b98e89339eb92bcdda752`. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958` approved it. A further phase is not authorized.

The desk is described in `docs/DESK.md`. The hosted FastAPI, React, and PostgreSQL target remains deferred. The recommended next phase, when separately approved, is still synthetic: load a real evidence set into the intelligence slots, and let the pages accept prices and FX rates. No fetched rates, recommendations, or forecasts follow from this desk.

No merge, push, deployment, financial connection, or purchase follows from this implementation.

## Historical

The following pointer was current before DESK-01. It is not the current next step.

PROTOTYPE-01 is a reviewed local paper ledger on branch `cursor/hm-01` at `afcd004c1a04f93711b4dac1163bf3d8a4c61996`. The baseline before the edits was `23c943ad50a88b4a0eb71fcd964798c9ddb321c4`. Reviewer `55bf7095-d00c-40fd-a475-d7d8b1b5932c` approved it. A further phase is not authorized.

The local pages and the synthetic fixture are described in `docs/LOCAL_PROTOTYPE.md`. The hosted FastAPI, React, and PostgreSQL target remains deferred. The recommended next phase, when separately approved, is still synthetic: enter prices and FX rates through the same pages, then add cost basis without tax-lot advice. No fetched rates, recommendations, or forecasts.

No merge, push, deployment, financial connection, or purchase follows from this implementation.

## Historical

The following pointer was current before PROTOTYPE-01. It is not the current next step.

ACCOUNTING-LEDGER is a reviewed local ledger on branch `cursor/hm-01` at `66a3e7644a2d74ebc749667fa88f94b27b721280`. The baseline before it was `a804f40181d5d8a89dd7f60982c5b63b936d18a8`. It is not merged. A further phase is not authorized.

The recommended next phase, when separately approved, is still synthetic: treat repeated statement rows as explicit breaks, then add cost basis without tax-lot advice. No fetched rates, recommendations, or forecasts.

No merge, push, deployment, financial connection, or purchase follows from this implementation.

## Historical

The following pointer was current before the accounting phase. It is not the current next step.

HM-02 is a reviewed local implementation on this branch at `a6c692fb9af18794c1acf7bd038847e8bd7d726a`. The walkthrough commit is `9a733369447c9e329a53e843de6e14526049acb5`. Neither commit is merged into the canonical repository. HM-03 is not authorized.

The recommended next slice, when separately approved, is synthetic supplied-rate conversion. A foreign-currency holding stays excluded unless an explicit finite Decimal rate is supplied with its own currency pair, exact as-of, and nonempty provenance. No fetched rates, transactions, forecasts, or recommendations belong in that slice until it is proposed and approved.

Do not treat this acceptance as canonical integration, deployment, or financial activation.

No merge, push, deployment, financial connection, or purchase follows from this implementation.

The following awaiting-approval text is retained as history. It is not the current next step.

1. Review HM_RECOMMENDED_DECISIONS.md on this card: recommendation is the existing 12-row architecture package, with proposed tactical/coverage settings provisional and no financial activation or purchase.
2. Approve or revise the architecture; separately authorize the saved synthetic-data accounting/coverage first milestone. These can be stated naturally here.
