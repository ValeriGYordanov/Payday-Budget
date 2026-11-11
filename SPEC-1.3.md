# Payday Budget — Specification v1.3: Forecasting

> Status: **complete**, 2026-11-11. 1.3.0 released; M23 dashboards verified on the Green.
> Approved 2026-11-11; all decisions in §10 confirmed (P1–P6 accepted as proposed). Extends `SPEC.md` (v1), `SPEC-1.1.md` and `SPEC-1.2.md` (it fills the §7
> placeholder there); everything there still applies unless changed here. Target version:
> **1.3.0** for the app and the integration.

## 1. Goal

Answer, for the current period, before the next payday:

| Question | Answer |
|---|---|
| How will the period end? | Projected end-of-period balance (§4.4) |
| Will each budget hold? | Per-budget outlook: a limit exceeded, a goal reached (§4.5) |
| How much can I spend? | Safe to spend per day (§4.6) |
| What is coming? | Upcoming recurring transactions and reminders (§4.7) |

Shown as dashboard cards, on the app dashboard (as for every chart, `SPEC.md` §8) and as sensors.

## 2. Scope

| In scope | Out of scope |
|---|---|
| Forecast for the current period only | Multi-period or yearly projections |
| Known items: recurring rules and reminders | Bank data, AI, seasonal models |
| Flexible spending from the last 3 closed periods | Projecting flexible (non-recurring) income |
| Sensors, one action, one WebSocket command, cards | Notifications or alerts on forecasts (automations can use the sensors) |

Nothing is stored: the forecast is computed on request from existing data. No migration.

## 3. Terms

- **Today** — the local date (P9). **Current period** — as in P1; no current period → no
  forecast (`404`, sensors `unknown`).
- **Expected next payday** `E` = current period start + **L**, where L is the average length of
  the last 3 closed periods, fallback 30 days — the rule the pace card already uses (D1).
  If `E` ≤ today, the period is **overdue**: `E` = today + 1.
- **Days left** `N` = `E` − today − 1: the days after today and before `E`.
- **Known items** — what the app knows will happen after today and before `E`:
  - occurrences of active recurring rules (R1; amount, kind, budget known);
  - due dates of active reminders (RM1), and reminder occurrences still open (due already,
    not yet recorded). Amount: the reminder's amount, else its last recorded amount (F3).
- **Flexible spending** — expenses not created by a recurring rule or recorded from a reminder.

## 4. Rules

Money stays integer minor units; every division rounds half up once, at the end (no drift).

- **F1** `E`, `L`, `N` and overdue as in §3.
- **F2** Known items: recurring occurrences with today < date < `E`; reminder due dates in the
  same range; open reminder occurrences (any due date). Archived categories or budgets don't
  matter here (the item is still expected).
- **F3** A reminder without an amount uses the amount of the last transaction recorded from
  it; with none, the item is listed with no amount and left out of the totals.
- **F4** Projected flexible spending, per budget = (flexible expenses of that budget in the
  last 3 closed periods) × `N` / (total days of those periods). No closed period yet →
  the current period so far: (flexible expenses since its start) × `N` / (days elapsed)
  (P1). Overdue (`N` = 0) → 0.
- **F5** Projected income = income so far + known income items. Flexible income is not
  projected.
- **F6** Projected expenses = expenses so far + known expense items + projected flexible.
  **Projected balance** = projected income − projected expenses.
- **F7** Per budget: projected target = projected income × the period's percent (B2, B3);
  projected spent = spent + its known expense items + its projected flexible; projected
  status by BD3 on those (`ok`/`over` for negative, `below`/`met` for positive).
- **F8** **Safe to spend per day** = max(0, projected income − expenses so far − known expense
  items − what positive budgets still need) / max(`N`, 1), where "still need" =
  Σ max(0, projected target − spent − its known items) over positive budgets (savings are
  set aside first) (P2).
- **F9** **Upcoming** lists every known item (F2) by date: date, name (reminder name, or the
  rule's description or category), kind, amount or null, budget, source (`recurring` /
  `reminder`), `due` (true for open reminder occurrences) and `estimated` (true when the
  amount is a reminder's last recorded one, F3; D6).

## 5. App

- `GET /api/v1/forecast` →
  `{period, expected_payday, overdue, days_left, basis: {periods, days}, income: {so_far,
  known, projected}, expenses: {so_far, known, flexible, projected}, balance_projected,
  safe_per_day, budgets: [{budget_id, name, direction, target, spent, known, flexible,
  projected_spent, projected_status}], series: [{date, balance, projected, items}],
  upcoming: [...]}`; amounts in minor units (`*_minor`). `series` is the §7 chart's data: the
  running balance per day, actual to today, then projected to the day before the payday
  (added at M20, D7).
- Dashboard: a **Forecast** card — projected balance, safe per day, expected payday, and the
  balance chart (§7) — and an **Upcoming** list. The progress bars get a projected-spent
  marker (P3).

## 6. Integration

| Entity / API | Value |
|---|---|
| `sensor.payday_budget_projected_balance` | monetary; attributes `projected_income`, `projected_expenses`, `overdue` |
| `sensor.payday_budget_safe_per_day` | monetary |
| `sensor.payday_budget_expected_payday` | `device_class: date`; attribute `days_left` |
| `sensor.payday_budget_upcoming` | number of known items; attribute `items` (unrecorded), money as decimal strings |
| `sensor.payday_budget_<budget>_projected` | monetary projected spent; attributes `projected_status`, `target` |
| `payday_budget.get_forecast` | action, `SupportsResponse.ONLY`: the forecast with money as decimal strings |
| `payday_budget/forecast` | WebSocket command for the cards |

The coordinator adds one request (`/forecast`) per refresh. Monetary sensors as in v1: no
`state_class`.

## 7. Cards

| Card | Shows |
|---|---|
| `payday-budget-forecast-card` | Headline: projected balance, safe per day, expected payday (days left). Chart: running balance from the period start to today (solid) and projected to `E` (dashed), known items as points. |
| `payday-budget-upcoming-card` | The upcoming list: date, name, amount ("?" when unknown), due ones first. Option `limit`. |
| `payday-budget-progress-card` | New option `forecast: true`: a marker for projected spent on each bar, coloured by projected status (P3). |

Options as v1 (`title`); the forecast always covers the current period.

## 8. Non-functional

- `/forecast` p95 < 200 ms with 20 000 transactions on HA Green; aggregation in SQL.
- Every rule F1–F9 has ≥ 1 automated test with the ID in its name; CI as before.
- No new dependencies; no migration.

## 9. Milestones

1. **M19 App forecast** — §3–§5 API and rules, tests.
2. **M20 Charts and cards** — app dashboard section, the two new cards, the progress marker.
3. **M21 Integration** — §6 sensors, action, WebSocket command, end-to-end test.
4. **M22 Release** — README, changelog, version 1.3.0, CI green, release, image.
5. **M23 HA dashboards** — forecast on the statistics view; scope agreed after M21 (P4).

## 10. Decisions

### Confirmed (2026-11-11)

| ID | Decision |
|---|---|
| D1 | Next payday = current start + average length of the last 3 closed periods (fallback 30). |
| D2 | Flexible spending projected from the last 3 closed periods' daily average. |
| D3 | All four answers: end-of-period balance, per-budget outlook, safe per day, upcoming. |
| D4 | Cards and the app dashboard, plus sensors. |
| D5 | A separate release, 1.3.0, with this spec. |
| D6 | Upcoming items carry `estimated` (amount from a reminder's history, F3), so the UI can show "≈". Added at M19. |
| D7 | `/forecast` returns `series` (daily running balance, actual then projected) for the forecast chart. Added at M20. |

### Proposals (accepted 2026-11-11)

| ID | Question | Decision |
|---|---|---|
| P1 | No closed period yet (first period): how to project flexible spending? | This period's pace so far; 0 on its first day |
| P2 | Safe per day: set aside what positive budgets (savings) still need? | Yes — savings first, the rest is spendable |
| P3 | Per-budget outlook in the UI | A projected marker on the existing progress bars (option on the card), not a new card |
| P4 | M23 dashboard scope | Agree after M21 |
| P5 | Reminders without an amount | The last recorded amount from that reminder; none → listed, not counted (F3) |
| P6 | Known income (recurring incomes) inside the window | Counted (F5); a payday income on `E` itself is not — it starts the next period |
