# Next Steps

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
