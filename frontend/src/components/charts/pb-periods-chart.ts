import type { ChartConfiguration, ChartDataset } from "chart.js";
import { t } from "../../i18n";
import type { CurrencyInfo } from "../../money";
import type { HistoryItem } from "../../types";
import { ChartElement, type Palette, moneyTick } from "./chart-base";

/** §8 periods: income vs expenses per period; optionally expenses stacked by budget. */
export class PbPeriodsChart extends ChartElement {
  static override properties = {
    items: { attribute: false },
    currency: { attribute: false },
    stacked: { type: Boolean },
  };
  declare items: HistoryItem[];
  declare currency: CurrencyInfo | null;
  declare stacked: boolean;

  constructor() {
    super();
    this.items = [];
    this.currency = null;
    this.stacked = false;
  }

  protected chartConfig(p: Palette): ChartConfiguration | null {
    if (!this.currency || this.items.length === 0) return null;
    const money = moneyTick(this.currency);
    const labels = this.items.map((i) => i.period.name);
    const income: ChartDataset<"bar"> = {
      label: t("dash.income"),
      data: this.items.map((i) => i.income_minor),
      backgroundColor: p.positive,
      stack: "income",
    };
    let expenses: ChartDataset<"bar">[];
    if (this.stacked) {
      const names = new Map<number, string>();
      for (const item of this.items) for (const b of item.budgets) names.set(b.budget_id, b.name);
      expenses = [...names].map(([id, name], index) => ({
        label: name,
        data: this.items.map((i) => i.budgets.find((b) => b.budget_id === id)?.spent_minor ?? 0),
        backgroundColor: p.series[index % p.series.length],
        stack: "expenses",
      }));
    } else {
      expenses = [
        {
          label: t("dash.expenses"),
          data: this.items.map((i) => i.expenses_minor),
          backgroundColor: p.negative,
          stack: "expenses",
        },
      ];
    }
    return {
      type: "bar",
      data: { labels, datasets: [income, ...expenses] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true, grid: { color: p.grid }, ticks: { callback: money, precision: 0 }, suggestedMax: 100 },
        },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12 } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y ?? 0)}` } },
        },
      },
    };
  }
}
customElements.define("pb-periods-chart", PbPeriodsChart);
