import type { ChartConfiguration } from "chart.js";
import { html } from "lit";
import { t } from "../../i18n";
import type { CurrencyInfo } from "../../money";
import type { Breakdown } from "../../types";
import { ChartElement, type Palette, moneyTick } from "./chart-base";

const MAX_SLICES = 7;

/** §8 category: donut of expenses by category for a period (optionally one budget). */
export class PbCategoryChart extends ChartElement {
  static override properties = {
    breakdown: { attribute: false },
    currency: { attribute: false },
  };
  declare breakdown: Breakdown | null;
  declare currency: CurrencyInfo | null;

  constructor() {
    super();
    this.breakdown = null;
    this.currency = null;
  }

  protected chartConfig(p: Palette): ChartConfiguration | null {
    const rows = this.breakdown?.categories ?? [];
    if (!this.currency || rows.length === 0) return null;
    const money = moneyTick(this.currency);
    const top = rows.slice(0, MAX_SLICES);
    const rest = rows.slice(MAX_SLICES).reduce((sum, r) => sum + r.amount_minor, 0);
    const labels = [...top.map((r) => r.name), ...(rest > 0 ? [t("chart.other")] : [])];
    const data = [...top.map((r) => r.amount_minor), ...(rest > 0 ? [rest] : [])];
    const config: ChartConfiguration<"doughnut"> = {
      type: "doughnut",
      data: {
        labels,
        datasets: [
          {
            data,
            backgroundColor: data.map((_, i) => p.series[i % p.series.length]),
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "60%",
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12 } },
          tooltip: { callbacks: { label: (c) => `${c.label}: ${money(Number(c.raw))}` } },
        },
      },
    };
    return config as unknown as ChartConfiguration;
  }

  override render() {
    if ((this.breakdown?.categories ?? []).length === 0) {
      return html`<p style="color: var(--pb-text-muted)">${t("chart.no_data")}</p>`;
    }
    return super.render();
  }
}
customElements.define("pb-category-chart", PbCategoryChart);
