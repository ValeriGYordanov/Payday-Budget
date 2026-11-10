# Changelog

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
