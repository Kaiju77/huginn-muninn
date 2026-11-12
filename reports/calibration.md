# Is the tool right? Walk-forward backtest

Entry rule: `after_news`. Each event is "predicted" from earlier events whose outcome was already known on its date, then scored against what happened. Brier score: lower is better; always saying 50% scores 0.250.

| Asset | Horizon | Predictions | Side right: event / baseline | Brier: event | Brier: baseline | Difference (95% interval) |
|---|---|---|---|---|---|---|
| Brent | 5 days | 13 | 4 / 8 | 0.279 | 0.244 | +0.035 (+0.004 to +0.070) |
| Brent | 20 days | 13 | 7 / 3 | 0.256 | 0.280 | -0.024 (-0.076 to +0.033) |
| Brent | 60 days | 13 | 7 / 3 | 0.256 | 0.295 | -0.039 (-0.095 to +0.025) |
| WTI | 5 days | 13 | 8 / 8 | 0.260 | 0.243 | +0.018 (-0.012 to +0.049) |
| WTI | 20 days | 13 | 4 / 4 | 0.310 | 0.269 | +0.041 (-0.029 to +0.117) |
| WTI | 60 days | 13 | 7 / 3 | 0.256 | 0.289 | -0.033 (-0.091 to +0.030) |
| Henry Hub gas | 5 days | 10 | 7 / 7 | 0.228 | 0.244 | -0.015 (-0.138 to +0.119) |
| Henry Hub gas | 20 days | 10 | 8 / 7 | 0.187 | 0.247 | -0.060 (-0.166 to +0.080) |
| Henry Hub gas | 60 days | 10 | 4 / 5 | 0.279 | 0.254 | +0.025 (-0.018 to +0.070) |
| USD/NOK | 5 days | 13 | 12 / 1 | 0.151 | 0.256 | -0.104 (-0.148 to -0.051) |
| USD/NOK | 20 days | 13 | 5 / 8 | 0.309 | 0.246 | +0.063 (-0.045 to +0.166) |
| USD/NOK | 60 days | 13 | 5 / 7 | 0.279 | 0.250 | +0.029 (+0.005 to +0.055) |

**How to read it.** Difference = event Brier minus baseline Brier; negative means the event base rate did better. Only an interval entirely below 0 is evidence of skill, and even then: there are 12 comparisons here, so one or two will look good by luck alone.

**Limits.** 10 to 13 predictions per row is very few. The event list was picked by hand with hindsight (see `data/events/README.md`), which can make event base rates look better than they would be live. The live prediction log is the real test.

_Historical backtest, not a forecast or advice._
