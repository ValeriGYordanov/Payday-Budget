# Changelog

## 1.3.0

- Forecast for the current period: expected next payday, projected
  end-of-period balance, safe to spend per day (savings set aside first),
  each budget's projected outlook and the upcoming recurring transactions
  and reminders. On the app dashboard, as new cards
  (`payday-budget-forecast-card`, `payday-budget-upcoming-card`, and
  `forecast: true` on the progress card) and as sensors and the
  `get_forecast` action.

## 1.2.0

- Budgets have a direction: negative (spend at most) or positive (reach at
  least, e.g. savings). Positive budgets below target show a warning, above it
  they are green. New binary sensor `<budget>_on_track`.
- Reminders: for bills that repeat with a different amount. Each due date shows
  a banner in the app, a Home Assistant notification and, optionally, a push to
  your phone (integration options); record it pre-filled or ignore it. New
  sensor `reminders` and actions `record_reminder` / `dismiss_reminder`.
- Backup: export everything to a zip and restore it (Settings, or the setup
  wizard on a new install), with a preview before anything is replaced.
- Suggestions when adding a transaction: the budget you usually use with the
  category, and your previous descriptions.
- Database migrations now run all-or-nothing.

## 1.1.0

- Categories in the API carry `transaction_count`, so it is clear which ones
  can be deleted.
- Integration: sensors for recent transactions, categories and budgets; the
  `list_transactions` action with filters; actions to add, update, archive and
  delete categories.
- Integration: a category, budget or tag name that matches more than one item
  is now an error instead of picking the first match.

## 1.0.0

First release.

- Budgeting periods that start when you say (payday), not on the 1st.
- Budgets as a share of income actually received, with per-period snapshots.
- Categories, tags, transactions and recurring transactions with catch-up.
- Web UI in the Home Assistant sidebar (Ingress): setup wizard, dashboard with
  charts, transactions, periods, budgets, categories, tags, recurring, settings.
- Home Assistant integration (via HACS): sensors, binary sensors, a button,
  actions and four dashboard cards. Discovered automatically.
