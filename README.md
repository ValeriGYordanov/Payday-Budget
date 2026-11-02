# Payday Budget

Budgeting for Home Assistant where the budgeting month (**period**) starts when
you get paid, not on the 1st of the month. Budgets are a percentage of the
income you actually received in that period.

It has two parts:

| Part | What it does |
|---|---|
| **App (add-on)** | Stores everything (SQLite), runs recurring transactions, and gives you the full UI in the Home Assistant sidebar. |
| **Integration (HACS)** | Sensors, binary sensors, a "start new period" button, actions for automations, and four dashboard cards. |

Requires Home Assistant OS or Supervised (for the app) and Home Assistant 2026.10 or newer.

## Install

### 1. The app

[![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FValeriGYordanov%2FPayday-Budget)

Or: **Settings → Apps → App store → ⋮ → Repositories**, add
`https://github.com/ValeriGYordanov/Payday-Budget`, then install **Payday Budget**
and start it. Open **Budget** in the sidebar and follow the setup wizard.

### 2. The integration

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ValeriGYordanov&repository=Payday-Budget&category=integration)

Or: **HACS → ⋮ → Custom repositories**, add
`https://github.com/ValeriGYordanov/Payday-Budget` as an **Integration**, then
download **Payday Budget** and restart Home Assistant.

Home Assistant then discovers the app: **Settings → Devices & services →
Discovered → Payday Budget → Add**. If it is not discovered, add the integration
manually with the app's host name (on the app's info page), port `8099` and the
token from **Budget → Settings → Integration token**.

## How it works

- A **period** runs from its start date to the day before the next period's
  start. The newest period is open-ended. Transactions belong to the period
  their date falls in; periods are never stored on transactions.
- New periods start only when you say so (button, action or UI), never
  automatically. Income that arrives before you press the button belongs to
  the previous period.
- Each period keeps a **snapshot** of the budget percentages. Editing a budget
  changes the current period and future ones; past periods stay as they were.
- **Target** = period income × budget %. **Remaining** = target − spent (can be
  negative). Unallocated = what is not assigned to any budget.
- Money is stored as integer minor units (cents); there are no floats anywhere.

## Entities

All on one device, **Payday Budget**.

| Entity | State |
|---|---|
| `sensor.payday_budget_period` | Period name; attributes `start_date`, `days_elapsed`, `period_id` |
| `sensor.payday_budget_period_start` | Start date |
| `sensor.payday_budget_income` / `_expenses` / `_balance` | Amounts in your currency |
| `sensor.payday_budget_unallocated` | Amount; attribute `percent` |
| `sensor.payday_budget_<budget>_target` / `_spent` / `_remaining` | Amounts per budget |
| `sensor.payday_budget_<budget>_used` | % of the target used (unavailable when the target is 0) |
| `binary_sensor.payday_budget_<budget>_over_target` | On when spent > target |
| `sensor.payday_budget_history` | Number of periods; attribute `history` with the last 12 |
| `button.payday_budget_start_new_period` | Starts a period dated today |

Amount sensors have no `state_class`: Home Assistant's long-term statistics are
calendar-based and don't fit periods.

## Actions

```yaml
action: payday_budget.add_transaction
data:
  kind: expense          # or income
  amount: 12.50          # in your currency, e.g. euros
  category: Food         # name or id
  budget: Needs          # name or id; expenses only
  date: "2026-11-02"     # optional, defaults to today
  description: Lidl      # optional
  tags: [groceries]      # optional
```

| Action | Fields | Returns |
|---|---|---|
| `payday_budget.add_transaction` | as above | `{id}` |
| `payday_budget.update_transaction` | `id` + any field above | `{id}` |
| `payday_budget.delete_transaction` | `id` | — |
| `payday_budget.start_period` | `date`, `name` (both optional) | `{id, name}` |
| `payday_budget.get_summary` | `period`: `current` (default), `previous` or an id | income, expenses, budgets… |

Rule violations raise an error that starts with the rule ID, e.g.
`P6: Transactions before the first period are not allowed`.

## Dashboard cards

The integration serves the cards itself; no extra resource to add.

```yaml
type: custom:payday-budget-progress-card   # target vs spent per budget
period: current                            # current | previous | id
budget: Needs                              # optional: one budget only
---
type: custom:payday-budget-periods-card    # income vs expenses per period
limit: 12
stacked: true                              # stack expenses by budget
---
type: custom:payday-budget-category-card   # spending by category
period: previous
budget: Wants                              # optional
---
type: custom:payday-budget-pace-card       # cumulative spend vs target pace
period: current
```

Every card also accepts `title`.

## Development

| Part | Location | Stack |
|---|---|---|
| App backend | `payday_budget/app` | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Integration | `custom_components/payday_budget` | Home Assistant 2026.10 (Python 3.14) |
| UI and cards | `frontend/` | TypeScript, Lit, Vite, Chart.js |

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python3.14 -m venv .venv-ha && .venv-ha/bin/pip install -r requirements-ha.txt
npm --prefix frontend ci
```

Checks (the same as CI):

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy payday_budget/app payday_budget/migrations tests/addon
.venv/bin/pytest
.venv-ha/bin/mypy --config-file tests/integration/mypy.ini
.venv-ha/bin/pytest -c tests/integration/pytest.ini tests/integration
npm --prefix frontend run build && npm --prefix frontend run lint && npm --prefix frontend test
```

`npm run build` writes the app UI to `payday_budget/app/static` and the cards to
`custom_components/payday_budget/www`. Both are committed; CI fails if they are
out of date.

For local runs, `.claude/launch.json` starts the backend (`backend`), the UI dev
server (`frontend`) and a local Home Assistant (`ha`).

## License

[MIT](LICENSE)
