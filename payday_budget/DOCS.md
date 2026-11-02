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
