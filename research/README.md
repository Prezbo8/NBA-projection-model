# Research log: what was tested, and the verdict

Protocol (Nov 8 2026): paper-traded strategies stay frozen. A new idea is judged by projection accuracy (MAE)
on the tune seasons; only clear winners get ONE look at the test seasons' lines, and become a new version
(v3, ...) with its own paper record. No tuning against betting results.

Era split (user decision Nov 8 2026: focus on 2021-26, when pace and scoring rose as offenses changed):
- from now on: **tune 2021-22 .. 2023-24, test 2024-25 .. 2025-26** (+ the live paper record)
  (`TUNE_SEASONS=2021-22,2022-23,2023-24 python src/team_model.py tune`)
- the 2015-21 results below are kept as history (the frozen v1 / v2 were tuned there).
- note: 2022-23 has no saved OPEN totals (Action Network 'open' book missing), so open-line tests use 2023-26.

## Team model
| Idea | Verdict | Numbers (tune MAE total / margin; base v1 14.671 / 10.078) |
|---|---|---|
| v1: pace x ppp ridge ratings, refit daily, HL 90, lam 5 | kept, **paper-traded (totals, edge >= 3)** | loses to CLOSE every season; vs OPEN ~53-54% 2007-26, streaky |
| v2: + missing-player value (availability.py) | kept, **paper-traded (spreads, edge >= 3)** | margin 10.078 -> 9.979; vs OPEN 57-62% is look-ahead (knows who sat), untestable on past data |
| + rest (2+ days off, 3-in-4, own/opp) | rejected | 14.697 / 10.101 |
| + travel km since last game (own/opp) | rejected | 14.679 / 10.088 |
| pace half-life 180 / 365 (longer) | rejected | 14.773 / 14.866 total |
| pace half-life 30 / 45 / 60 (shorter) | not adopted: noise-sized | 14.703 / 14.671 / 14.656 (best -0.015) |
| modern-era retune (tuned 2021-24): half-life 25, lam 5 for totals | **rejected on the 2024-26 test** | tune MAE total 14.833 -> 14.671 (grid flat at HL 20-30), but test 2024-26 MAE 14.64 / 15.05 (v1) vs 14.67 / 15.04: gain gone. vs OPEN edge>=3: v1 1,100 bets 54.8% +51.2u, retune 1,157 bets 54.4% +43.8u; both lose to CLOSE |
| **v1 totals report card 2023-26** (`research/grade_totals.py`, fresh v1 backtest, no look-ahead) | **B at the open, F at the close** | vs OPEN edge>=3: 1,785 bets 55.2% +97.4u (+5.5%, z +2.4); seasons 55.9 / 52.1 / 57.6%; overs 54.7%, unders 55.9%; the close moved toward the model 63% of the time (avg +2.36 pts); max drawdown 43.7u, 15/21 winning months. vs CLOSE: 1,950 bets 48.6% -7.2%. v1 is more accurate than the open (14.81/14.65/15.06 vs 15.18/14.62/15.14), less than the close. NOTE: data/backtest/team_preds.csv is v2 (has look-ahead) |
| **v3 totals** (`with_v3`, ablate_v3 'D'): points-based missing value (missing points + missing minutes, fitted separately = learned replacement level) in ppp own/opp AND in pace | **kept, paper-traded (totals, edge >= 3) from Nov 8 2026** | tune 2021-24 MAE total: v1 14.833, v2 14.842, B (v2 + pace) 14.807, C (pts) 14.804, **D 14.746**. Test 2024-26 (v1/v2/D only): 14.844 / 14.829 / **14.779** (2024-25 14.640 -> 14.554, 2025-26 15.049 -> 15.004); margin 10.83 (v2 10.90). A 25-pt scorer out moves the total about -2 (own -1.8, opp +1, pace -1.2). Vs-lines test impossible (look-ahead: knows who sat), so paper only |

## Pace vs totals (research/pace_totals.py, 2021-22 .. 2025-26 regular season, 6,150 games)
- In-game: pace explains ~28% of the variance in totals (25% 2021-22 rising to 32% 2025-26), efficiency the rest
  (r pace~total 0.50, r ppp~total 0.81). +1 possession per team ~ +1.9 points.
- Pre-game: v1 pace predicts actual pace r 0.44; pre-game pace alone ~ total r 0.30 (v1 total r 0.37).
- Market: the closing total already tracks pre-game pace (r 0.65); pre-game pace vs (actual - close) r 0.007,
  over rate by pace quintile 48-52% vs close and 46-53% vs open, regression t +0.6 = **pace is fully priced**.
  Same regression: v1 edge vs the close has coefficient -0.10 (t -2.1), i.e. v1's disagreement with the close is
  slightly anti-predictive (matches its F at the close).

## Props
| Idea | Verdict | Numbers |
|---|---|---|
| props v1: minutes x per-minute rates x pace x opponent | no edge | lines beat model MAE in every market; ROI -2..-9% vs close and open (2023-26, ~50k bets/market) |
| minutes boost from missing teammates | rejected | every boost > 0 made MAE worse (fixed eval set) |
| P(over) with fitted outcome variance | adopted for display only | still overconfident; market no-vig better calibrated (Brier .243 vs .255) |

## Ideas not yet tested (need new data)
- Referees (totals: fouls / free throws): backfill STOPPED by the user Nov 8 2026 (low expected value; the market
  prices crews). Saved: data/refs 2015-16 .. 2018-19 complete, 2019-20 partial. refs.yml is disabled (Actions >
  nba.com referees > Enable to resume; it skips saved games). Game-day snapshots still record refs from Nov 8 2026 on.
- Player-based team ratings (lineup / on-off or RAPM-style), roster-based preseason priors.
