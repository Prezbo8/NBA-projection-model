# Research log: what was tested, and the verdict

Protocol (Nov 8 2026): paper-traded strategies stay frozen. A new idea is judged on the tune seasons
(2015-16 .. 2020-21) by projection accuracy (MAE); only clear winners get ONE look at the 2021-26 lines,
and become a new version (v3, ...) with its own paper record. No tuning against betting results.

## Team model
| Idea | Verdict | Numbers (tune MAE total / margin; base v1 14.671 / 10.078) |
|---|---|---|
| v1: pace x ppp ridge ratings, refit daily, HL 90, lam 5 | kept, **paper-traded (totals, edge >= 3)** | loses to CLOSE every season; vs OPEN ~53-54% 2007-26, streaky |
| v2: + missing-player value (availability.py) | kept, **paper-traded (spreads, edge >= 3)** | margin 10.078 -> 9.979; vs OPEN 57-62% is look-ahead (knows who sat), untestable on past data |
| + rest (2+ days off, 3-in-4, own/opp) | rejected | 14.697 / 10.101 |
| + travel km since last game (own/opp) | rejected | 14.679 / 10.088 |
| pace half-life 180 / 365 (longer) | rejected | 14.773 / 14.866 total |
| pace half-life 30 / 45 / 60 (shorter) | not adopted: noise-sized | 14.703 / 14.671 / 14.656 (best -0.015) |

## Props
| Idea | Verdict | Numbers |
|---|---|---|
| props v1: minutes x per-minute rates x pace x opponent | no edge | lines beat model MAE in every market; ROI -2..-9% vs close and open (2023-26, ~50k bets/market) |
| minutes boost from missing teammates | rejected | every boost > 0 made MAE worse (fixed eval set) |
| P(over) with fitted outcome variance | adopted for display only | still overconfident; market no-vig better calibrated (Brier .243 vs .255) |

## Ideas not yet tested (need new data)
- Referees (totals: fouls / free throws): historical crews need ~1 nba.com request per game via the Mac runner;
  game-day snapshots record refs from Nov 8 2026 on.
- Player-based team ratings (lineup / on-off or RAPM-style), roster-based preseason priors.
