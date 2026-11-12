# Is the tool right? Walk-forward backtest

Entry rule: `after_news`. Each event is "predicted" from earlier events whose outcome was already known on its date, then scored against what happened. Brier score: lower is better; always saying 50% scores 0.250.

| Asset | Horizon | Predictions | Side right | Brier: event base rate | Brier: normal-period baseline | Brier: 50% |
|---|---|---|---|---|---|---|
| Brent | 5 days | 13 | 4/13 | 0.279 | 0.244 | 0.250 |
| Brent | 20 days | 13 | 7/13 | 0.256 | 0.280 | 0.250 |
| Brent | 60 days | 13 | 7/13 | 0.256 | 0.295 | 0.250 |
| WTI | 5 days | 13 | 8/13 | 0.260 | 0.243 | 0.250 |
| WTI | 20 days | 13 | 4/13 | 0.310 | 0.269 | 0.250 |
| WTI | 60 days | 13 | 7/13 | 0.256 | 0.289 | 0.250 |
| Henry Hub gas | 5 days | 10 | 7/10 | 0.228 | 0.244 | 0.250 |
| Henry Hub gas | 20 days | 10 | 8/10 | 0.187 | 0.247 | 0.250 |
| Henry Hub gas | 60 days | 10 | 4/10 | 0.279 | 0.254 | 0.250 |
| USD/NOK | 5 days | 13 | 12/13 | 0.151 | 0.256 | 0.250 |
| USD/NOK | 20 days | 13 | 5/13 | 0.309 | 0.246 | 0.250 |
| USD/NOK | 60 days | 13 | 5/13 | 0.279 | 0.250 | 0.250 |

How to read it: the event base rate is only useful if its Brier score is clearly below both the baseline and 50%. With this few predictions, differences under about 0.03 are noise.

_Historical backtest, not a forecast or advice._
