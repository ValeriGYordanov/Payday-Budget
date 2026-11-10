/** Shapes returned by the add-on REST API (/api/v1). Money is integer minor units. */

export type Kind = "income" | "expense";
export type Frequency = "weekly" | "monthly" | "yearly";

export interface Settings {
  currency: string;
  minor_unit: number;
  setup_completed: boolean;
}

export interface Currency {
  code: string;
  minor_unit: number;
}

export interface Period {
  id: number;
  name: string;
  start_date: string;
  end_date: string | null;
  is_current: boolean;
  days_elapsed: number;
  created_by_id: string | null;
  created_by_name: string | null;
  created_at: string;
}

export interface PeriodDetail extends Period {
  budgets: { budget_id: number; name: string; archived: boolean; percent: string; direction: Direction }[];
}

/** v1.2 BD1: negative = spend at most the target; positive = reach at least it. */
export type Direction = "negative" | "positive";

/** BD3 */
export type BudgetStatus = "ok" | "over" | "below" | "met";

export interface Budget {
  id: number;
  name: string;
  percent: string;
  direction: Direction;
  sort_order: number;
  archived: boolean;
  created_at: string;
}

export interface BudgetList {
  items: Budget[];
  allocated_percent: string;
  unallocated_percent: string;
}

export interface Category {
  id: number;
  name: string;
  kind: Kind;
  icon: string;
  archived: boolean;
  transaction_count: number;
}

export interface Tag {
  id: number;
  name: string;
}

export interface User {
  id: string;
  name: string | null;
}

export interface Transaction {
  id: number;
  kind: Kind;
  amount_minor: number;
  date: string;
  period_id: number | null;
  category_id: number;
  category_name: string;
  budget_id: number | null;
  budget_name: string | null;
  description: string | null;
  tags: string[];
  recurring_rule_id: number | null;
  occurrence_date: string | null;
  created_by_id: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecurringRule {
  id: number;
  kind: Kind;
  amount_minor: number;
  category_id: number;
  category_name: string | null;
  budget_id: number | null;
  budget_name: string | null;
  description: string | null;
  tags: string[];
  frequency: Frequency;
  interval: number;
  anchor_date: string;
  end_date: string | null;
  active: boolean;
  last_generated_date: string | null;
}

export interface BudgetRow {
  budget_id: number;
  name: string;
  archived: boolean;
  percent: string;
  target_minor: number;
  spent_minor: number;
  remaining_minor: number;
  percent_used: string | null;
  over_target: boolean;
  direction: Direction;
  status: BudgetStatus;
  on_track: boolean;
}

export interface Summary extends Settings {
  period: Period;
  income_minor: number;
  expenses_minor: number;
  balance_minor: number;
  unallocated: { percent: string; amount_minor: number };
  budgets: BudgetRow[];
}

export interface HistoryItem {
  period: Period;
  income_minor: number;
  expenses_minor: number;
  budgets: {
    budget_id: number;
    name: string;
    target_minor: number;
    spent_minor: number;
    direction: Direction;
    status: BudgetStatus;
  }[];
}

export interface Breakdown {
  period: Period;
  budget_id: number | null;
  total_minor: number;
  categories: { category_id: number; name: string; icon: string; amount_minor: number }[];
}

export interface Daily {
  period: Period;
  pace_length_days: number;
  days: { date: string; spent_minor: number; cumulative_minor: number }[];
}
