# R11 Chronological Lab Report

Moscow date: 2026-11-11. Mode `historical-small`. Lab run 1 on database `tmn_r11_lab`.

PUBLISH ENABLED? NO. TELEGRAM SEND COUNT? 0. LIVE DATA? NO.

## What changed versus R10

R10 `load_lab()` imported every event for the final day at once. Day 1, 15 and 30 therefore showed the same 30 clusters / 23 posts. R11 imports only events with `available_at <= lab_now(N)` and writes one `lab_daily_snapshots` row per day.

## Historical-small counts

| Day | Source items | Clusters | Posts | Future skipped |
| --- | ---: | ---: | ---: | ---: |
| 1 | 3 | 2 | 2 | 0 |
| 15 | 25 | 17 | 17 | 0 |
| 30 | 50 | 42 | 42 | 0 |

Daily snapshots: 30. Episodes (proposed slots): 37. Published messages: 0.

The stream is a **golden set of ≥40 labelled DEMO events** plus fillers. It is not a market frequency and must not be divided by 30 to invent a “posts per day” KPI.

## Channel desk (day 30)

| Channel | Clusters | Posts | Slots |
| --- | ---: | ---: | ---: |
| ai_news | 5 | 5 | 4 |
| ai_tools | 4 | 4 | 4 |
| github | 5 | 5 | 4 |
| cyber | 6 | 6 | 6 |
| infra | 4 | 4 | 4 |
| homelab | 7 | 7 | 5 |
| dev | 6 | 6 | 5 |
| future | 5 | 5 | 5 |

Empty calendar cells stay `пусто: нет материала`. That is an honest vacancy, not a hidden skip of a ready post.

## Two modes

- `historical-small` — title kept `offline-30d` so R10 idempotent tests still find the run. Sparse, labelled, honest gaps.
- `stress-30d` — separate `LabRun` title `offline-30d-stress-30d`. Synthetic weekday density for durability, not audience proof.

Export: `reports/r11/lab-daily.json`, `reports/r11/lab-daily.csv`, `reports/r11-lab-results.json`.
