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
