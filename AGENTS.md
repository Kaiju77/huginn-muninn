# Agent guidance

- Read `README.md` and `PROJECT_STATE.md` before making changes.
- Use the shared harness under `C:\Users\kaiar\Documents\projects\ai-dev-harness`.
- Work in isolated branches or worktrees; never push or merge automatically.
- Do not commit credentials, generated files, caches, or local model data.
- Keep changes bounded and require explicit validation before handoff.

## Current checkout

This worktree is `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01` on branch `cursor/hm-01`. INGEST-04 is the reviewed CPI freshness note and stored-series inventory at `41b7175e5f771934d10dd1921a60ee0b3f6e097d`. Independent review on 2026-10-11 approved INGEST-04. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594`. INGEST-05 is the reviewed USD/NOK gap note and future-date sentence at `ffdb4096b83fc9417a95a78f1b4833d7ad717732`. It places the newest stored USD/NOK observation beside the synthetic ledger rate 10.25 and adds the future-date sentence. Independent review on 2026-10-11 approved INGEST-05. Reviewer `a3090eaf-710a-40ca-8a86-d26c3075a5c4`. INGEST-03 is the reviewed NOWA chart, EUR/NOK difference, and CPI cell at `fd11a8b358ed67fcd142620b9bdb5a71fa251821`. It adds a NOWA chart, a two-source EUR/NOK difference, and one Statistics Norway CPI cell. Independent review on 2026-10-11 approved INGEST-03. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5`. INGEST-02 is the reviewed five-series refresh at `6b2e10e7d33eb762a2f9b2734729777475e8fe7d`, described in `docs/INGEST.md`. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff` approved it on 2026-10-11. INGEST-01 is the reviewed read-only ingestion layer at `d9cad72ab052ca6d1e2517c4d7ebef918e783a3c`. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30` approved it on 2026-10-11. Norges Bank, the ECB, and the one Statistics Norway cell can be refreshed explicitly. Other SSB tables remain unconnected. SEC EDGAR is prepared. FRED stays blocked. Open human decisions are in `HUMAN_TASKS.md`. The evidence-register commit is `1f6f26750c0b196aaea57d2f70c9edb2833628d7`, described in `docs/EVIDENCE.md`. Independent review on 2026-10-11 approved that register. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120`. The night-desk commit is `83750c9c6ec98a48fd24c864ee2cea184a37cf15`.

The paper-ledger commit is `afcd004c1a04f93711b4dac1163bf3d8a4c61996`, described in `docs/LOCAL_PROTOTYPE.md` and `docs/DECIMAL_RULES.md`. The accounting ledger commit remains `66a3e7644a2d74ebc749667fa88f94b27b721280`. The snapshot commit remains `a6c692fb9af18794c1acf7bd038847e8bd7d726a`. Independent review on 2026-10-10 approved the paper ledger. Reviewer `55bf7095-d00c-40fd-a475-d7d8b1b5932c`. The canonical handoff remains read-only at `C:/Users/kaiar/Documents/projects/huginn-muninn/docs/DIRECT_PROJECT_HANDOFF.md`.

## Historical checkout note

The following paragraph described this checkout before HM-02 implementation.

This worktree is `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01` on branch `cursor/hm-01` at commit `a718922de94aebfc4a44b5e38e3ab3b7bd4cd7a4`. The synthetic demonstration is described in `docs/HM01_WALKTHROUGH.md`. A later slice is proposed in `docs/HM02_PROPOSAL.md`. HM-02 is not started. The canonical handoff remains read-only at `C:/Users/kaiar/Documents/projects/huginn-muninn/docs/DIRECT_PROJECT_HANDOFF.md`.
