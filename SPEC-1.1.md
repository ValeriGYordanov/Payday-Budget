# Payday Budget — Specification v1.1

> Status: approved, 2026-11-02. All decisions in §9 confirmed. Extends `SPEC.md` (v1); everything there
> still applies unless changed here. Target version: **1.1.0** for the app and the
> integration (released together; the version test keeps them in sync).

## 1. Goal

Expose **transactions** and **category management** to Home Assistant, so the
placeholder notes on the user's finance dashboard can be replaced with working cards:

| View | Placeholder today | Replaced by |
|---|---|---|
| `finance` | "New Payday Budget expected - will show recent transactions here" | Recent transactions sensor (§4.1) |
| `finance-transactions` | "… will show transactions with filters, edit and delete here" | List action (§4.3) + existing edit/delete actions |
| `finance-settings` | "… will manage categories here" | Categories sensor (§4.2) + category actions (§4.4) |
| `finance` (form) | Dropdowns filled through a REST call with the token | Categories and budgets sensors (§4.2, §4.5) |

No change to periods, budgets, recurring rules or money handling. Money stays integer
minor units in the app; in HA attributes and action responses it is an exact decimal
string (v1 decision: HA's JSON has no `Decimal`, floats are not used).

## 2. Scope

| In scope | Out of scope (unchanged from v1 or later) |
|---|---|
| Recent transactions, categories and budgets as HA sensors | Category hierarchy (parents) and merge — not Payday Budget concepts |
| Listing transactions with filters via an action | Tag and budget management from HA (budgets are read-only, §4.5) |
| Adding, editing, archiving and deleting categories via actions | CSV import, receipt photos, bank sync (v2 list in `SPEC.md` §10) |
| Transaction count per category in the app API | Visual card editors, translations other than English |

## 3. App changes (add-on)

Small, read-only API addition; no schema change, no new migration.

- **A1** `GET /api/v1/categories` items gain `transaction_count` (int): number of
  transactions with that category, any period. Computed in SQL (one grouped count),
  not per row. Lets HA show whether a category can be deleted (C2) before trying.
- **A2** `GET /api/v1/categories/{id}` returns the same field.
- No other endpoint changes: `/transactions` (filters, pagination), `/tags`,
  `PATCH`/`DELETE` on transactions and categories already exist.

## 4. Integration changes

All new data comes through the existing coordinator (refreshed on SSE `changed`,
fallback poll every 5 min); actions call the app and then request a refresh, as in v1.
The new sensors belong to the existing "Payday Budget" device.

### 4.1 Sensor: recent transactions

`sensor.payday_budget_recent_transactions`

| Property | Value |
|---|---|
| State | Number of transactions in the current period (`total` of `/transactions?period=current`) |
| Attribute `transactions` | The newest **N** transactions across all periods (§9 D1), newest date first, then newest id |
| Item fields | `id`, `date`, `kind`, `amount` (decimal string), `currency`, `category`, `category_id`, `budget`, `budget_id`, `description`, `tags` (names), `created_by` (name or null), `recurring` (bool) |
| Recorder | `transactions` is in `_unrecorded_attributes` |
| No current period | State `unknown`; attribute still lists recent transactions |

### 4.2 Sensor: categories

`sensor.payday_budget_categories`

| Property | Value |
|---|---|
| State | Number of non-archived categories |
| Attribute `categories` | All categories, sorted by kind (expense first) then name |
| Item fields | `id`, `name`, `kind`, `icon`, `archived`, `transaction_count` |
| Recorder | `categories` is in `_unrecorded_attributes` |

### 4.3 Action: list transactions

`payday_budget.list_transactions` — `SupportsResponse.ONLY`.

| Field | Meaning |
|---|---|
| `period` | `current`, `previous` or a period id (same resolution as `get_summary`) |
| `date_from`, `date_to` | Inclusive dates |
| `kind` | `income` or `expense` |
| `category` | Name or id (name resolved within `kind` when given; ambiguous name → error, §5 TL3) |
| `budget` | Name or id |
| `tag` | Tag name or id |
| `user` | HA user id (`created_by`) |
| `search` | Text in the description (case-insensitive) |
| `limit` | 1–500, default 100 |
| `offset` | ≥ 0, default 0 |

Response: `{ "total": int, "limit": int, "offset": int, "items": [ … ] }` with items in
the §4.1 shape. All fields optional; no filters = newest transactions overall.

Editing and deleting reuse the v1 actions `payday_budget.update_transaction` and
`payday_budget.delete_transaction` (no change).

### 4.4 Actions: category management

| Action | Fields | Response |
|---|---|---|
| `payday_budget.add_category` | `name`, `kind`, `icon?` (default `mdi:tag`) | optional: `{id}` |
| `payday_budget.update_category` | `category` (name or id), `kind?` (to disambiguate a name, or to change kind), `name?`, `icon?`, `archived?` | optional: `{id}` |
| `payday_budget.delete_category` | `category` (name or id), `kind?` (to disambiguate) | — |

- Changing `kind` of a category with transactions → rule error **C1** (v1 rule).
- Deleting a category with transactions → rule error **C2** (v1 rule); archive it instead.
- Duplicate name within a kind → error `conflict`.
- Errors raise `ServiceValidationError` with the rule ID or error code, as in v1.

### 4.5 Sensor: budgets (D3)

`sensor.payday_budget_budgets` — read-only; budgets are still managed in the app.

| Property | Value |
|---|---|
| State | Number of non-archived budgets |
| Attribute `budgets` | All budgets in the app's order (`sort_order`, then name) |
| Item fields | `id`, `name`, `percent` (decimal string, e.g. `"50.00"`), `archived`, `sort_order` |
| Recorder | `budgets` is in `_unrecorded_attributes` |

Uses the budgets list the coordinator already fetches; no extra request.

### 4.6 WebSocket

No new commands in this version (§9 D2, D4).

## 5. Rules

Every rule ID needs ≥ 1 automated test whose name contains the ID (as in v1).

- **A1** Category list items carry `transaction_count`, computed in one SQL query.
- **RT1** The recent-transactions attribute holds at most N items, newest first.
- **RT2** Recent-transactions amounts are exact decimal strings with the currency's minor
  units (e.g. `"45.50"`, JPY `"1500"`); no floats.
- **RT3** The recent-transactions state is the current period's transaction count;
  `unknown` when there is no current period.
- **TL1** `list_transactions` passes each filter to the app unchanged in meaning and
  returns `total` / `limit` / `offset` / `items` in the §4.1 item shape.
- **TL2** `period: previous` resolves like `get_summary`; no previous period → error.
- **TL3** A category or budget given by name resolves case-insensitively; a category name
  that exists in both kinds without `kind` given → error, nothing is called.
- **CM1** `add_category` / `update_category` / `delete_category` act on the app and
  refresh the categories sensor.
- **CM2** Rule violations from the app (C1, C2) surface as `ServiceValidationError`
  carrying the rule ID.
- **CM3** Archived categories stay in the categories sensor (`archived: true`) and stay
  selectable for filtering; they are not offered for new transactions (v1 rule).
- **BS1** The budgets sensor lists every budget (archived ones with `archived: true`) in
  the app's order; its state counts only non-archived budgets; percents are decimal
  strings.

## 6. Home Assistant dashboard updates (required)

Version 1.1 is not done until the user's HA dashboards use it. These changes are not
shipped in the app or the integration; they are delivered as YAML (milestone M11, §8).
The user's views are in Bulgarian and use Mushroom and flex-table cards.

### 6.1 Changes per view

- **`finance`**: the old "Последни транзакции" flex-table reads
  `sensor.payday_budget_recent_transactions` → `transactions`; the placeholder note goes.
- **`finance-transactions`**: filter helpers (search, from/to, type, category, budget)
  drive a trigger-based template sensor in `finance.yaml` that calls
  `list_transactions` and stores `items`; the table lists them; pencil/delete call
  scripts that wrap `update_transaction` / `delete_transaction`. The old
  "ръчна / импортирана" distinction is dropped: every transaction is editable.
- **`finance-settings`**: the table reads `sensor.payday_budget_categories`; add,
  rename, icon, hide (= archive) and delete call the §4.4 actions. "Родител",
  "Премести" and "Слей" are removed (not supported, §2).
- **`finance.yaml`**: the category dropdowns read `sensor.payday_budget_categories` and
  the budget dropdown reads `sensor.payday_budget_budgets` instead of the REST call; the
  `rest_command` and the `payday_budget_auth` secret are removed.
- **All three views**: the placeholder notes ("New Payday Budget expected - …") and the
  old cards kept as reminders are removed once their replacement works.

### 6.2 Steps (M11)

1. **Update the software first.** Update the app to 1.1.0 (app store) and the
   integration to 1.1.0 (HACS), restart HA, and check that
   `sensor.payday_budget_recent_transactions`, `sensor.payday_budget_categories` and
   `sensor.payday_budget_budgets` exist and have their attributes.
2. **Update `finance.yaml`** (`/homeassistant/packages/finance.yaml`):
   - dropdown sync from the new sensors instead of `rest_command.payday_budget_get`;
   - remove `rest_command`, then remove `payday_budget_auth` from `secrets.yaml`;
   - add the filter helpers, the trigger-based template sensor that calls
     `list_transactions`, and the edit/delete scripts for `finance-transactions`;
   - add the category helpers and scripts for `finance-settings`.
3. **Check and restart**: Developer tools → YAML → Check configuration, then restart.
4. **Replace the views**, one full YAML per view pasted into the raw configuration
   editor: `finance`, `finance-transactions`, `finance-settings`. `finance-budget` and
   `finance-stats` stay as they are unless a change above affects them.
5. **Verify on the Green**:
   - `finance`: the recent-transactions table shows the newest 10; the form still saves
     (dropdowns filled from the sensors).
   - `finance-transactions`: each filter narrows the list; edit saves and the row
     changes; delete asks for confirmation and removes the row.
   - `finance-settings`: add, rename, change icon, archive/unarchive work; delete of a
     category with transactions shows the C2 error; the dropdowns on `finance` follow.
   - No "Entity not available" or "Action not found" left on any finance view, and no
     `rest_command` errors in the HA log.

### 6.3 Process

Same as the v1 dashboard work: questions before writing anything (no assumptions),
`finance.yaml` checked with HA's config check, templates rendered against a local HA
with Payday Budget 1.1.0 before delivery, and the old view YAML kept by the user until
the new one is verified.

## 7. Non-functional

- Performance targets from `SPEC.md` §9 still hold: with 20 000 transactions,
  `/categories` with counts and `/transactions?limit=100` stay under 200 ms p95 on HA Green.
- The coordinator adds two requests per refresh (recent transactions, categories); the
  budgets sensor reuses the budgets request it already makes.
- New sensors' list attributes are unrecorded (no database growth in HA).
- Strings for the new actions and sensors in `strings.json` / `translations/en.json`.
- CI as in v1 (ruff, mypy, eslint, tsc, tests, image build, hassfest, HACS).

## 8. Milestones

Same process as v1: one milestone at a time, tests and linters passing, review stop.

1. **M8 App** — A1/A2 (`transaction_count`), tests.
2. **M9 Integration** — §4.1–§4.5, tests including an end-to-end run against the real app.
3. **M10 Release** — README and changelog, version 1.1.0, CI green, release published,
   app image built.
4. **M11 HA dashboards** — `finance.yaml` and the `finance`, `finance-transactions` and
   `finance-settings` views updated and verified on the Green (§6.2). Version 1.1 is
   complete only after this milestone.

## 9. Decisions (confirmed 2026-11-02)

| ID | Question | Decision |
|---|---|---|
| D1 | How many recent transactions in the sensor? Newest overall, or newest in the current period only? | **N = 10**, newest overall (like the old table) |
| D2 | Also ship a `payday-budget-transactions-card` (filters, edit, delete built in) instead of building it from helpers and flex-table? | No — dashboard approach (§6, M11); a card can follow later |
| D3 | Add `sensor.payday_budget_budgets` so `finance.yaml` no longer needs the REST call and token? | Yes (§4.5) |
| D4 | Should `list_transactions` also be available as a WebSocket command for custom cards? | No |
| D5 | Default `limit` for `list_transactions` | 100 (the old view showed the first 100) |
| D6 | Version number | 1.1.0 (new features, nothing removed) |
