# Payday Budget — Specification v1

> Working name / domain: **Payday Budget** / `payday_budget` — rename before first public release.
> Status: approved, 2026-11-01. All decisions in §12 confirmed.

## 1. Goal

Home Assistant budgeting tool where the **budgeting month (period) starts when the user says** (salary day), not on the 1st of the calendar month. Budgets are a percentage of income actually received. Exposes sensors, a button, actions and charts to HA. Personal first, open-source-ready.

## 2. Glossary

| Term | Meaning |
|---|---|
| Period | Budgeting month. Starts on `start_date`, ends the day before the next period's `start_date`. The latest period is open-ended. |
| Current period | Period with the greatest `start_date` ≤ today. |
| Budget | Named share of income, in % (e.g. Needs 50, Wants 30, Savings 20). |
| Income (of a period) | Sum of income transactions dated inside the period. Actual received only, never planned. |
| Target | Period income × budget % (snapshot for that period). |
| Unallocated | 100 % − sum of budget %. Allowed to be > 0. |

## 3. Architecture

Monorepo with two installable parts and a shared frontend package.

| Part | Responsibility |
|---|---|
| **Add-on** | Single source of truth. SQLite DB, REST API, SSE events, recurring scheduler, full web UI via Ingress (HA sidebar). |
| **Custom integration** (HACS) | Entities (sensors, binary sensors, button), actions, WebSocket API for cards, serves the dashboard cards. Stores only connection config — no business data. |
| **Frontend package** | Shared Lit web components + charts. Built twice: add-on SPA and one cards bundle for the integration. |

### 3.1 Repository layout

```
/
├── repository.yaml              # HA add-on repository manifest
├── hacs.json                    # HACS manifest (integration)
├── payday_budget/               # add-on
│   ├── config.yaml
│   ├── Dockerfile
│   ├── app/                     # FastAPI backend
│   └── migrations/              # Alembic
├── custom_components/payday_budget/   # integration
│   └── www/                     # built cards bundle (generated)
├── frontend/                    # shared TS/Lit source
└── tests/
```

### 3.2 Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, SQLite (WAL) |
| Frontend | TypeScript, Lit, Vite, Chart.js |
| Integration | Python, HA `DataUpdateCoordinator`, `aiohttp` |
| Target hardware | HA Green (aarch64, 4 GB RAM, eMMC). Build archs: `aarch64`, `amd64`. |

## 4. Data model

Money is stored as **integer minor units** (`amount_minor`). No floats for money anywhere.
**A period is never stored on a transaction** — it is always derived from dates.

| Table | Fields |
|---|---|
| `settings` | `currency` (ISO 4217, default `EUR`), `setup_completed` |
| `periods` | `id`, `start_date` DATE UNIQUE, `name`, `created_by_id`, `created_by_name`, `created_at` |
| `budgets` | `id`, `name` UNIQUE, `percent` NUMERIC(5,2), `sort_order`, `archived`, `created_at` |
| `period_budgets` | `period_id`, `budget_id`, `percent` — PK (`period_id`, `budget_id`) |
| `categories` | `id`, `name`, `kind` (`income`\|`expense`), `icon` (`mdi:*`), `archived` — UNIQUE (`name`, `kind`) |
| `tags` | `id`, `name` UNIQUE |
| `transactions` | `id`, `kind` (`income`\|`expense`), `amount_minor` INT > 0, `date` DATE, `category_id`, `budget_id` NULL, `description` NULL (≤ 500), `recurring_rule_id` NULL, `occurrence_date` NULL, `created_by_id`, `created_by_name`, `created_at`, `updated_at` |
| `transaction_tags` | `transaction_id`, `tag_id` |
| `recurring_rules` | `id`, `kind`, `amount_minor`, `category_id`, `budget_id` NULL, `description`, `tag_ids`, `frequency` (`weekly`\|`monthly`\|`yearly`), `interval` ≥ 1, `anchor_date`, `end_date` NULL, `active`, `last_generated_date` NULL |

Indexes: `transactions(date)`, `transactions(budget_id, date)`, `transactions(category_id, date)`, UNIQUE `transactions(recurring_rule_id, occurrence_date)`.

## 5. Business rules

Every rule ID below must have ≥ 1 automated test whose name contains the ID.

### 5.1 Periods

- **P1** A transaction belongs to the period with the greatest `start_date` ≤ `transaction.date`.
- **P2** `start_date` is unique. A future `start_date` is rejected.
- **P3** A new period is created only manually: HA button (start = today) or action `start_period(date?, name?)`. No automatic start.
- **P4** Default name: `<Month> <YYYY>` of `start_date` (English). On collision, append ` (2)`, ` (3)`… Renamable.
- **P5** `start_date` is editable (P2 applies). Deleting a period merges its transactions into the previous period. Deleting the earliest period is rejected if transactions would end up before the first period.
- **P6** Transactions dated before the earliest period's `start_date` are rejected. The first-run setup wizard requires creating the first period.
- **P7** Income dated before the button is pressed belongs to the previous period (consequence of P1). No special handling.
- **P8** Changing a transaction date or a period `start_date` re-buckets immediately. No data migration.
- **P9** All dates are local dates in HA's timezone (`TZ` from Supervisor). No time-of-day is stored or used.

### 5.2 Budgets

- **B1** `percent` 0–100 with 2 decimals. The sum of non-archived budgets must be ≤ 100; otherwise rejected.
- **B2** `target = period income × period_budgets.percent / 100`.
- **B3** Snapshot: creating a period copies the current `percent` of every non-archived budget into `period_budgets`. Editing a budget % updates the default for future periods **and** the current period's snapshot; past periods do not change. A backdated period inserted between two existing periods copies the snapshot of the period it splits.
- **B4** Budgets with transactions can only be archived, not deleted. Archived budgets cannot be chosen for new transactions, are excluded from new snapshots, and still appear in past periods.
- **B5** `spent` = sum of expense transactions with that budget in the period. `remaining = target − spent` (may be negative). `percent_used = spent / target × 100`; target 0 → unavailable.
- **B6** Expenses require a budget. Incomes must not have a budget.
- **B7** Savings is an ordinary budget. Money moved to savings is logged as an expense with the Savings budget.

### 5.3 Categories

- **C1** A category has a `kind` (`income`\|`expense`). Categories are **not** linked to budgets. The budget is chosen on every transaction.
- **C2** Categories with transactions can only be archived.
- **C3** First-run seed (editable): income — Salary, Other income; expense — Housing, Food, Transport, Health, Utilities, Entertainment, Shopping, Savings transfer, Other.

### 5.4 Transactions

- **T1** `amount_minor` > 0. The sign comes from `kind`.
- **T2** Required: `kind`, `amount`, `category` (same kind), `date` (default today), `budget` (expense only). Optional: `description`, `tags`.
- **T3** `created_by` is the HA user (from Ingress headers or from the action call context). Shown in lists.
- **T4** Every HA user can create, edit and delete any transaction and all settings.

### 5.5 Recurring transactions

- **R1** Frequencies: `weekly`, `monthly`, `yearly`, each with `interval` N. For monthly rules, if the anchor day doesn't exist in a month, use that month's last day.
- **R2** The scheduler runs on add-on start and daily at 00:05 local time. It generates every occurrence from `last_generated_date + 1` (or `anchor_date`) up to and including today, so missed days are caught up after downtime. Idempotent via UNIQUE (`recurring_rule_id`, `occurrence_date`).
- **R3** Generated transactions are normal transactions. Editing a rule does not change already-generated ones. Deleting a generated transaction does not regenerate it.
- **R4** Never generate future-dated transactions.
- **R5** Occurrences before the earliest period are skipped and logged.

### 5.6 Currency

- **K1** One currency per install, ISO 4217, default `EUR`, chosen in the setup wizard.
- **K2** Minor-unit exponent follows the currency (EUR 2, JPY 0…). The currency can be changed later only if the exponent is the same. Changing it relabels only — no conversion — and requires confirmation.

## 6. Add-on

### 6.1 `config.yaml` (key settings)

- `ingress: true`, `panel_icon: mdi:wallet`, `panel_title: Budget`
- `panel_admin: false` — non-admin HA users must see the panel (default is admin-only)
- `hassio_api: true` (Supervisor discovery)
- `backup: cold` (consistent SQLite backup; data lives in `/data`)
- `arch: [aarch64, amd64]`, no host ports exposed by default
- Option: `log_level`

### 6.2 Auth

- Ingress requests: accept only from `172.30.32.2`. User from `X-Remote-User-Id`, `X-Remote-User-Name`, `X-Remote-User-Display-Name`.
- Integration requests: `Authorization: Bearer <token>`. The token is generated on first start and stored in `/data`. The integration passes the acting HA user in `X-Acting-User-Id` / `X-Acting-User-Name`.
- Everything else: `401`.

### 6.3 Discovery

- On start, POST to Supervisor `/discovery` with service `payday_budget` and `{host, port, token}`.
- **To verify in M3:** Supervisor accepts discovery for a custom-integration domain. If not, fall back to a manual config flow (host, port, token). The token is shown in the add-on UI → Settings.

### 6.4 REST API (`/api/v1`)

- CRUD: `/periods`, `/budgets`, `/categories`, `/tags`, `/transactions`, `/recurring`
- `/settings`, `/setup`
- Reads: `/summary?period=current|<id>`, `/periods/history?limit=N`, `/breakdown?period=&budget=`, `/daily?period=`
- `/transactions` supports filters (`period`, `date_from`, `date_to`, `kind`, `category`, `budget`, `tag`, `user`, `q`) and pagination.
- `GET /events` — SSE. Emits `changed` after every write and after scheduler runs.
- Errors: JSON `{code, message, field?}`. Rule violations return `422` with the rule ID in `code` (e.g. `P6`).

### 6.5 Storage

- `/data/payday_budget.db`, WAL mode, Alembic migrations applied automatically on start.

### 6.6 UI (Ingress)

- Pages: Setup wizard (currency, first period, budgets) · Dashboard (current period + all charts from §8, period switcher) · Transactions (filterable list, add/edit/delete) · Periods (list with start/end/name, start new, edit, rename, delete) · Budgets (sum indicator, unallocated shown) · Categories · Tags · Recurring · Settings.
- "Add transaction" button on every page. Field order: kind, amount, category, budget, date, description, tags. Budget is never prefilled.
- Mobile-first: must work at 360 px width (Fold cover screen). Light/dark via `prefers-color-scheme`.

## 7. Integration

### 7.1 Basics

- Manifest: `domain: payday_budget`, `config_flow: true`, `iot_class: local_push`.
- Config flow: `hassio` discovery step + manual step (§6.3).
- Updates: `DataUpdateCoordinator` loads on startup and refreshes on every SSE `changed` event. Fallback polling every 5 min. The SSE connection reconnects with backoff.
- Entities become `unavailable` when the add-on is unreachable.
- Budget entities are added and removed dynamically as budgets are created or archived.
- Cards are served from `custom_components/payday_budget/www` via `async_register_static_paths` + `add_extra_js_url`. No separate frontend install.

### 7.2 Entities (single device "Payday Budget")

| Entity | State | Notes |
|---|---|---|
| `sensor.payday_budget_period` | period name | attrs: `start_date`, `days_elapsed`, `period_id` |
| `sensor.payday_budget_period_start` | date | `device_class: date` |
| `sensor.payday_budget_income` | amount | monetary |
| `sensor.payday_budget_expenses` | amount | monetary |
| `sensor.payday_budget_balance` | income − expenses | monetary |
| `sensor.payday_budget_unallocated` | amount | monetary; attr `percent` |
| `sensor.payday_budget_<budget>_target` | amount | monetary |
| `sensor.payday_budget_<budget>_spent` | amount | monetary |
| `sensor.payday_budget_<budget>_remaining` | amount | monetary |
| `sensor.payday_budget_<budget>_used` | % | `state_class: measurement` |
| `binary_sensor.payday_budget_<budget>_over_target` | on if spent > target | for automations |
| `sensor.payday_budget_history` | number of periods | attr `history`: last 12 periods (income, expenses, per-budget target/spent); listed in `_unrecorded_attributes` |
| `button.payday_budget_start_new_period` | — | starts a period dated today |

- Monetary sensors: `device_class: monetary`, unit = install currency, **no `state_class`**. HA long-term statistics are calendar-based and don't fit periods.

### 7.3 Actions

| Action | Fields | Response |
|---|---|---|
| `payday_budget.add_transaction` | `kind`, `amount`, `category`, `budget` (expense), `date?`, `description?`, `tags?` | optional: `{id}` |
| `payday_budget.update_transaction` | `id` + any field above | optional |
| `payday_budget.delete_transaction` | `id` | — |
| `payday_budget.start_period` | `date?` (default today), `name?` | optional: `{id, name}` |
| `payday_budget.get_summary` | `period?` (`current`\|`previous`\|id) | required: summary object |

- `category` / `budget` accept a name or an id. The acting user comes from `call.context.user_id`.
- Rule violations raise `ServiceValidationError` with the rule ID.

### 7.4 WebSocket commands (used by cards)

`payday_budget/summary`, `payday_budget/history`, `payday_budget/breakdown`, `payday_budget/daily` — proxied to the add-on API.

## 8. Charts

Same components in the add-on UI and as dashboard cards.

| Component / card | Shows |
|---|---|
| `payday-budget-progress-card` | Per budget: target vs spent bars, plus unallocated. |
| `payday-budget-periods-card` | Income vs expenses per period, last N (default 12). Optional stacking by budget. |
| `payday-budget-category-card` | Donut by category for a period, optional budget filter. |
| `payday-budget-pace-card` | Cumulative daily spend in the period vs a linear target line. Line length = average length of the last 3 closed periods (fallback 30 days). |

Card YAML options: `period` (`current`\|`previous`\|id), `budget`, `limit`, `title`. Visual editors are v2.

## 9. Non-functional

- Performance on HA Green with 20 000 transactions: API p95 < 200 ms, UI first load < 2 s on LAN, add-on idle RAM < 150 MB. All aggregation in SQL.
- Tests: pytest for rules (§5) and API; `pytest-homeassistant-custom-component` for the integration; cards build smoke test.
- CI (GitHub Actions): ruff, mypy, eslint, tsc, tests, multi-arch image build, `hassfest`, HACS validation.
- License MIT. English only in v1; translation structure ready (integration `strings.json`, UI i18n keys).
- Backups: everything in `/data`, included in HA backups.

## 10. Scope

| v1 | v2 (out of scope now) |
|---|---|
| Periods, budgets, categories, tags, transactions, recurring, currency, add-on UI + charts, integration entities/actions/button, 4 cards | CSV import, bank/notification auto-capture, card visual editors, Bulgarian translation, multi-currency, roles/permissions |

## 11. Milestones

Each milestone ends with passing tests/linters and a review stop.

1. **M1 Backend core** — schema, migrations, rules §5.1–5.4 and §5.6, REST API, setup endpoint, tests.
2. **M2 Recurring** — rules, scheduler, catch-up, tests.
3. **M3 Add-on packaging** — Dockerfile, `config.yaml`, Ingress auth, token, discovery (verify §6.3), SSE. Installs and runs on HA Green.
4. **M4 Add-on UI** — all pages from §6.6 and charts from §8.
5. **M5 Integration** — config flow, coordinator + SSE, entities, button, actions, WebSocket commands.
6. **M6 Cards** — 4 cards bundled and served by the integration.
7. **M7 Release** — README (install add-on repo + HACS), CI, validation, `v1.0.0`.

## 12. Decisions (confirmed 2026-11-01)

- Name/domain `Payday Budget` / `payday_budget`.
- Stack in §3.2 (you said you don't mind).
- B3 per-period % snapshot (alternative: percentages apply to all periods retroactively).
- P2 no future period starts. P6 transactions before the first period are rejected.
- T4 every HA user can edit everything, including settings.
- K2 currency change only relabels, same exponent only.
- Pace-card line length rule (§8).
- Monetary sensors without `state_class` (no long-term statistics).
- CSV import moved to v2 — you chose "manual only for start", which conflicts with "extras are perfect".
