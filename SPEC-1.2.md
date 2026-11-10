# Payday Budget — Specification v1.2

> Status: **approved**, 2026-11-10. All decisions in §10 confirmed (P1–P9 accepted as proposed). Extends `SPEC.md` (v1) and `SPEC-1.1.md`; everything there still applies
> unless changed here. Target version: **1.2.0** for the app and the integration.

## 1. Goal

| Feature | Why |
|---|---|
| Budget direction (§3) | Savings and investing are "at least X %", spending is "at most X %". Today every budget is judged as spending. |
| Reminders (§4) | Bills that repeat with a different amount each time (electricity, some credits) can't be recurring rules. A reminder asks for the transaction instead of creating it. |
| Export and import (§5) | Users can back up and restore their data in Payday Budget's own format. |
| Suggestions (§6) | Faster entry from history. Last milestone. |
| Forecasting (§7) | Placeholder; specified after this draft is confirmed. |

## 2. Scope

| In scope | Out of scope |
|---|---|
| Budget direction (positive / negative), on-track status, UI explanation | Bank sync and automatic import (any format other than our own) |
| Reminders: rules, due occurrences, HA notification + push, sensor, completion in the app UI | Rules and auto-categorization (v3 or v4) |
| Export and import of all data in our own format | Custom reports |
| Suggestions from history (last milestone) | Changes to recurring rules (they stay as they are) |
| Forecasting: placeholder only | Merging an import into existing data |

## 3. Budget direction

### 3.1 Data

- `budgets.direction`: `negative` (spend at most the target) or `positive` (reach at least the
  target). Existing budgets become `negative` (migration `0002`).
- `period_budgets.direction`: snapshotted with `percent` (B3), so past periods keep the
  direction they had (P1).

### 3.2 Rules

- **BD1** A budget has a direction, `negative` or `positive`; default `negative`.
- **BD2** The snapshot (B3) copies `direction` with `percent`; editing a budget's direction
  changes the current and future periods, never past ones (same as a % edit).
- **BD3** Status per budget in a period:

  | Direction | `spent` vs `target` | `status` | Meaning |
  |---|---|---|---|
  | negative | ≤ target | `ok` | within the limit |
  | negative | > target | `over` | bad |
  | positive | < target | `below` | warning (not reached yet) |
  | positive | ≥ target | `met` | good (more is better) |

  `on_track` = status is `ok` or `met`.
- **BD4** B1 (sum ≤ 100 %) applies to all budgets regardless of direction; B2, B5 unchanged.
- **BD5** `over_target` keeps its v1 meaning (`spent > target`) for every direction (§10 D4).

### 3.3 API

- `/budgets` items and bodies: `direction`.
- `/summary` budget rows: `direction`, `status`, `on_track`. `/periods/history` budget rows:
  `direction`, `status`.

### 3.4 Integration

| Entity | State | Notes |
|---|---|---|
| `binary_sensor.payday_budget_<budget>_on_track` | on when `on_track` (BD3) | new; dynamic like the other budget entities |
| `binary_sensor.payday_budget_<budget>_over_target` | unchanged | BD5 |
| `sensor.payday_budget_<budget>_target` | unchanged | new attribute `direction` |
| `sensor.payday_budget_budgets` | unchanged | items gain `direction` |

`get_summary` budget rows gain `direction`, `status`, `on_track`.

### 3.5 UI and cards

- **Budgets tab**: a direction selector per budget, with a short explanation under it:
  - *Negative — spend at most this share of income. Going over is bad.*
  - *Positive — reach at least this share of income (e.g. savings, investing). Going over is good.*
- **Setup wizard**: the suggested Savings budget defaults to `positive`; others `negative`
  (P2).
- **Progress card and dashboard bars**: colour by status — `ok` neutral, `over` red,
  `below` amber, `met` green.

## 4. Reminders

A reminder repeats like a recurring rule (R1) but never creates a transaction. On each due
date it opens an **occurrence**; the user completes it (records a transaction from pre-filled
data) or ignores it.

### 4.1 Data

| Table | Fields |
|---|---|
| `reminders` | `id`, `name` (≤ 100), `kind`, `amount_minor` NULL, `category_id` NULL, `budget_id` NULL, `description` NULL, `tag_ids`, `frequency`, `interval` ≥ 1, `anchor_date`, `end_date` NULL, `active`, `last_opened_date` NULL, `created_at` |
| `reminder_occurrences` | `id`, `reminder_id`, `due_date`, `status` (`open`\|`recorded`\|`dismissed`), `transaction_id` NULL, `notified_at` NULL, `closed_at` NULL — UNIQUE (`reminder_id`, `due_date`) |

### 4.2 Rules

- **RM1** Due dates follow R1 (frequency, interval, anchor, month-end clamping).
- **RM2** The scheduler (R2: on start and daily at 00:05) opens an occurrence for every due date
  from `last_opened_date + 1` up to and including today; missed days are caught up. A **new**
  reminder opens only its latest due date on or before today (D11). Due dates before the first
  period are skipped, as in R5 (D12). Idempotent via UNIQUE (`reminder_id`, `due_date`). Never
  for future dates.
- **RM3** All pre-filled fields are optional; `kind` and `name` are required. Completing an
  occurrence records an ordinary transaction (T1–T4 apply) with the date defaulting to
  `due_date`, and sets `status = recorded` and `transaction_id`.
- **RM4** Ignoring sets `status = dismissed`. A closed occurrence (`recorded` or `dismissed`)
  never reopens; deleting the recorded transaction does not reopen it.
- **RM5** Editing a reminder affects only occurrences opened afterwards. Deleting a reminder
  deletes its open occurrences; recorded transactions stay.
- **RM6** Archived categories and budgets in a reminder's pre-fill are not used for the new
  transaction (C2, B4): those fields come up empty.
- **RM7** Each open occurrence is notified once (`notified_at`), through every configured
  channel (§4.4). Closing it removes its persistent notification.

### 4.3 App

- **API**: CRUD `/reminders`; `GET /reminders/occurrences?status=open`;
  `POST /reminders/occurrences/{id}/record` (transaction body; missing fields from the
  pre-fill) → the transaction; `POST /reminders/occurrences/{id}/dismiss`;
  `POST /reminders/occurrences/{id}/notified`. SSE `changed` after each.
- **UI**:
  - Recurring tab gets a **Reminders** section (list, add, edit, delete, active toggle).
  - Open occurrences show as a banner on every page; tapping one opens the Add transaction
    form pre-filled from the reminder, with **Record** and **Ignore**.
  - The notification links to the app panel; the banner is the way in. No deep link: HA's
    Ingress panel drops the URL hash (checked on the Green, 2026-11-10; P3).

### 4.4 Integration

- **Sensor** `sensor.payday_budget_reminders`: state = number of open occurrences;
  attribute `reminders` (unrecorded): `id`, `reminder_id`, `name`, `due_date`, `kind`,
  `amount` (decimal string or null), `currency`, `category`, `budget`, `description`.
- **Notifications** (sent by the integration when it sees an occurrence without
  `notified_at`, then marked notified):
  - HA persistent notification, id `payday_budget_reminder_<occurrence id>`; dismissed when
    the occurrence is closed.
  - Push via the `notify` services chosen in the integration's **options** (§4.5).
  - Text: reminder name, due date, pre-filled amount if any; link to the app panel.
- **Actions**:

  | Action | Fields | Response |
  |---|---|---|
  | `payday_budget.record_reminder` | `occurrence`, then any of `amount`, `category`, `budget`, `date`, `description`, `tags` | `{transaction_id}` |
  | `payday_budget.dismiss_reminder` | `occurrence` | — |

  So dashboards and automations can act on the sensor (P4).

### 4.5 Integration options (push target)

- New options flow: **Notify services** — a multi-select of the existing
  `notify.mobile_app_*` services (and other `notify.*` services); empty by default.
- With none selected, only the persistent notification and the sensor are used.
- A selected service that no longer exists is skipped and logged as a warning.

## 5. Export and import

### 5.1 Format

- One `.zip` file: `manifest.json` plus one CSV per table: `settings`, `periods`, `budgets`,
  `period_budgets`, `categories`, `tags`, `transactions`, `transaction_tags`,
  `recurring_rules`, `reminders`, `reminder_occurrences` (P5).
- `manifest.json`: `format` (= 1), `app_version`, `exported_at`, `currency`, row counts.
- CSV: UTF-8, header row, comma separator, RFC 4180 quoting. Money as integer minor units,
  percents as decimal strings (`"50.00"`), dates ISO 8601. IDs kept, so references survive.

### 5.2 Rules

- **EX1** Export includes all data; the file name is `payday-budget-<YYYY-MM-DD>.zip`.
- **EX2** Import **replaces** all data, after a confirmation that names what is replaced
  (row counts from the manifest vs. current data). No merge.
- **EX3** Import is all-or-nothing: one database transaction; any error rolls back and the
  previous data stays.
- **EX4** Import validates the manifest (`format` supported) and every row against the v1
  rules (P2, P6, B1, C1, T1–T2, R1, RM1…). The first error is reported with file, row and rule
  ID.
- **EX5** A file from a newer `format` is rejected; older formats are migrated on import.
- **EX6** After an import the scheduler runs once (recurring and reminders catch up).

### 5.3 API and UI

- `GET /api/v1/export` → the zip. `POST /api/v1/import?confirm=false|true` with the zip as the
  raw request body (`application/zip`), so no multipart dependency is added (P6).
  `confirm=false` validates the whole file and returns the row counts (file vs. now) without
  changing anything; `confirm=true` replaces (D14).
- UI: Settings → **Backup** — Export button; Import (file picker → preview with counts or the
  first error → **Replace**). The setup wizard offers the same **Restore from backup** (D13).
- Not exposed to HA (no actions, no entities).

## 6. Suggestions from history (last milestone)

Accepted as below; details are re-checked when the milestone starts (P7):

- **SG1** In the Add transaction form, after a category is chosen, the budget most often used
  with that category in the last 90 days is offered as a one-tap suggestion (never
  pre-selected: "Budget is never prefilled" from v1 stays).
- **SG2** The description field offers previous descriptions for the chosen category, most
  recent first.
- **SG3** Suggestions come from SQL over existing transactions; nothing new is stored.

## 7. Forecasting (placeholder)

To be specified after this draft is confirmed. Target: cards for the statistics dashboard on
the user's HA Green. Not part of the 1.2.0 milestones until specified.

## 8. Non-functional

- Performance targets from `SPEC.md` §9 still hold; export of 20 000 transactions < 5 s on HA
  Green, import < 15 s (P8).
- One migration (`0002`) for §3.1 and §4.1; existing data keeps working unchanged.
- No new dependencies (zip and csv are in the standard library).
- Every rule ID in §3–§6 has ≥ 1 automated test with the ID in its name; CI as in v1.

## 9. Milestones

Same process: one milestone at a time, tests and linters passing, review stop.

1. **M12 Budget direction** — §3: migration, rules, API, UI, integration entities, card colours.
2. **M13 Reminders (app)** — §4.1–§4.3: data, scheduler, API, UI.
3. **M14 Reminders (integration)** — §4.4–§4.5: sensor, notifications, options flow, actions.
4. **M15 Export and import** — §5.
5. **M16 Suggestions** — §6.
6. **M17 Release** — README, changelog, version 1.2.0, CI green, release published, image built.
7. **M18 HA dashboards** — scope to be agreed (P9).

## 10. Decisions

### Confirmed (2026-11-10)

| ID | Decision |
|---|---|
| D1 | Out: automatic import / bank sync, custom reports; rules and auto-categorization later (v3/v4). |
| D2 | Budget direction: positive (at least, more is good) and negative (at most, more is bad), with an explanation in the Budgets tab. |
| D3 | A positive budget below its target shows a warning. |
| D4 | Keep `over_target`; add a separate on-track entity. |
| D5 | Recurring rules stay as they are; reminders are separate. |
| D6 | A reminder is completed in the app UI (pre-filled form); notified via HA persistent notification **and** push; also a sensor. |
| D7 | Export and import only in Payday Budget's own format, for backup and restore. |
| D8 | Suggestions are the last milestone; forecasting is discussed after this spec. |
| D9 | Version 1.2.0. |
| D10 | Push targets are chosen in the integration's options (notify services). |
| D11 | A new reminder opens only its latest due date on or before today, not every date since its first date (catch-up after downtime is unchanged). |
| D12 | Reminder due dates before the first period are skipped (they could only be ignored, P6). |
| D13 | The setup wizard also offers "Restore from backup", so a backup can be restored onto a fresh install. |
| D14 | Import is preview-then-confirm: picking a file validates it and shows counts (file vs. now) or the first error; nothing changes until Replace. |

### Proposals (accepted 2026-11-10)

| ID | Question | Decision |
|---|---|---|
| P1 | Snapshot `direction` per period like `percent`? | Yes, so past periods keep their meaning |
| P2 | Setup wizard: suggested Savings budget defaults to positive? | Yes |
| P3 | Notification link: deep link to the occurrence? | Only if Ingress keeps the URL hash. Checked on the Green (2026-11-10): it doesn't (`/app/<slug>#/recurring` opened the dashboard), so the notification links to the app and the banner is the way in |
| P4 | `record_reminder` / `dismiss_reminder` actions in HA? | Yes, so dashboards and automations can act on the sensor |
| P5 | Backup file: zip of per-table CSVs, or one transactions-only CSV? | Zip of all tables (a real backup) |
| P6 | Import upload without a multipart dependency? | Raw `application/zip` body |
| P7 | Suggestions SG1–SG3 as above? | Confirm at M16 |
| P8 | Export / import time targets | < 5 s / < 15 s for 20 000 transactions on HA Green |
| P9 | M18: which dashboard changes (on-track sensors, reminders on `finance`)? | Agree after M14 |
