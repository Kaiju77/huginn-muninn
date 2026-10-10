# Huginn & Muninn

Local implementation repository for the ChatGPT project **HUGIIN & MUNIN**.

This repository is prepared for the shared AI development harness. Product scope and implementation decisions should be captured in `PROJECT_STATE.md` before feature work begins.

This isolated `cursor/hm-01` branch preserves the accepted HM-01 slice: discoverable synthetic tests and an explicit known Decimal subtotal with completeness. The HM-01 `Portfolio` still does not qualify currency, as-of, or provenance. The separate HM-02 snapshot does. Conversion and coverage qualification remain unfinished. The branch is not merged into the canonical Huginn & Muninn repository.

## Run the HM-01 walkthrough

From the checkout root, `python scripts/hm01_walkthrough.py` prints the synthetic demonstration. What the output means, and the offline sandbox command, are in `docs/HM01_WALKTHROUGH.md`.

`docs/HM02_SNAPSHOT.md` describes the separate qualified snapshot in this checkout. Independent review approved that snapshot on this branch. It is not merged.
