# Payday Budget

## First start

Open **Budget** in the sidebar. The setup wizard asks for:

1. **Currency** — one per install. It can be changed later only to a currency
   with the same number of decimals, and only relabels amounts.
2. **First period** — the day your budgeting month starts, usually your last
   payday. Transactions before it are not allowed.
3. **Budgets** — shares of income, e.g. Needs 50 %, Wants 30 %, Savings 20 %.
   The total may be below 100 %; the rest is "unallocated".

## Periods

A period runs from its start date to the day before the next period starts.
Start a new one when you get paid: **Periods → Start new period**, the
integration's **Start new period** button, or the `payday_budget.start_period`
action. Periods never start automatically.

Income received before you start the new period belongs to the previous one.

## Budgets

Each period keeps its own copy of the budget percentages. Changing a budget
changes the current period and future ones, never past periods. Savings is an
ordinary budget: move money to savings by adding an expense with that budget.

## Recurring transactions

Weekly, monthly or yearly, every N weeks/months/years. They are created on
start and daily at 00:05; days the add-on was off are caught up.

## Budget direction

Each budget is **negative** (spend at most this share of income; going over is
bad) or **positive** (reach at least this share, e.g. savings or investing;
going over is good). Like the percentage, the direction is kept per period.

## Reminders

**Recurring → Reminders**: for bills that repeat with a different amount (e.g.
electricity). On each due date the reminder appears as a banner on every page,
pre-filled with what you set (category, budget, amount if known). Record it or
ignore it. A new reminder starts with its latest due date only; due dates
before your first period are skipped.

## Forecast

For the current period, the dashboard shows a **Forecast**: the next payday is
expected after the average length of your last 3 periods (30 days at first).
Until then it counts what is known — recurring transactions, reminders (their
amount, or the last one you recorded) — plus your usual flexible spending
from the last 3 periods. You see the projected balance, how much is safe to
spend per day after what savings still need, a marker on each budget bar, and
everything coming up before payday. Nothing is stored; it updates as you go.

## Backup and restore

**Settings → Backup → Export** downloads everything as a zip (one CSV per table).
**Restore from backup** checks the file first and shows what it contains; nothing
changes until you press **Replace all data**. On a new install, the setup wizard
offers the same restore. Home Assistant backups include the add-on's data too.

## Integration

Install **Payday Budget** from HACS. Home Assistant discovers the add-on
automatically. If not, add the integration manually with the add-on's host name
(shown on this page under "Hostname"), port 8099 and the token from
**Budget → Settings → Integration token**.

## Options

- `log_level` — `trace`, `debug`, `info` (default), `notice`, `warning`,
  `error` or `fatal`.

## Backups

All data lives in the add-on's `/data` folder and is part of Home Assistant
backups. The add-on stops briefly during a backup so the database is consistent.
