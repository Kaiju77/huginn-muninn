# Event catalogs

One CSV per category. Loaded and validated by `src/huginn_muninn/catalog.py`.

| column | meaning |
|---|---|
| `event_id` | unique id, `me-YYYY-short-name` |
| `date_public` | the date the news broke, in European/US trading time. If it broke after the Brent close, use the next day. |
| `episode` | crisis this event belongs to. Events in one episode are not independent; a study counts one per episode (`first_per_episode`). |
| `source_url` | where the date comes from |
| `source_checked` | `yes` once a person (or a web check) has confirmed the link and the date |

## mideast-conflict.csv

28 events in 21 episodes, 1988-2026. All are after 1987-05-20, when EIA daily Brent begins.

**Known bias (read before trusting a number):** the events were chosen by hand from well-known crises. Crises become well known partly *because* oil moved, so this list probably overstates the effect. The list deliberately includes cases where oil fell (2003 invasion of Iraq, 1991 Desert Storm), but the fix is a rule-based list. v2 will rebuild it from UCDP conflict data with a fixed threshold.

## mideast-conflict-ucdp.csv (rule-based, generated)

Built by `scripts/build_ucdp_catalog.py` from `data/ucdp/ged_mideast.csv`, which `scripts/fetch_ucdp.py` downloads from the UCDP GED API (version 26.1, 1989-2025; needs `UCDP_TOKEN`; runs in GitHub Actions). Do not edit by hand; change the rule and rebuild. The rule and its reasons are documented in `src/huginn_muninn/ucdp_events.py`.

**Rule.** For each country (Iran, Iraq, Israel incl. Palestine, Lebanon, Syria, Yemen, Saudi Arabia, Kuwait, UAE, Qatar, Bahrain, Oman, Libya, Jordan), add up GED best-estimate deaths per day. An **onset** is the first day on which the 7-day sum reaches 25, after 90 days in which the 7-day sum stayed below 25. One event per onset. Defaults: all violence types (1-3), rows dated to within a week (`date_prec` <= 3), each row placed on its `date_end` (the last possible date).

- `date_public` = onset day + 1. GED dates are when the violence happened; reports and death tolls reach markets later.
- `episode`: onsets in any country within 30 days of the previous one share an episode, so a regional war counts once in a study.
- Onsets whose 90-day calm period starts before 1989-01-01 (GED's first day) are dropped.
- `source_url` is the UCDP country page; `notes` holds the death count and every rule parameter.

**Limits.** Selection uses GED's retrospective (revised) death counts, not what was known on the day. Final GED stops on 31 Dec of the previous year; recent onsets need the GED Candidate data, not fetched yet.
