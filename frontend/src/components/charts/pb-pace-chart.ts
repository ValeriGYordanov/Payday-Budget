import type { ChartConfiguration } from "chart.js";
import { t } from "../../i18n";
import type { CurrencyInfo } from "../../money";
import type { Daily } from "../../types";
import { ChartElement, type Palette, moneyTick } from "./chart-base";
import { paceTarget } from "./pace";
import { define } from "../../define";

/**
 * §8 pace: cumulative daily spend vs a linear target line. The line rises from 0 to
 * the period's total target over `pace_length_days`, then stays flat.
 */
export class PbPaceChart extends ChartElement {
  static override properties = {
    ...ChartElement.properties,
    daily: { attribute: false },
    targetMinor: { type: Number },
    currency: { attribute: false },
  };
  declare daily: Daily | null;
  declare targetMinor: number;
  declare currency: CurrencyInfo | null;

  constructor() {
    super();
    this.daily = null;
    this.targetMinor = 0;
    this.currency = null;
  }

  protected chartConfig(p: Palette): ChartConfiguration | null {
    if (!this.daily || !this.currency) return null;
    const money = moneyTick(this.currency);
    const length = Math.max(this.daily.pace_length_days, 1);
    const days = Math.max(this.daily.days.length, length);
    const labels = Array.from({ length: days }, (_, i) => t("chart.day", { day: i + 1 }));
    return {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: t("chart.cumulative"),
            data: this.daily.days.map((d) => d.cumulative_minor),
            borderColor: p.primary,
            backgroundColor: p.primary,
            pointRadius: 0,
            borderWidth: 2,
            fill: false,
          },
          {
            label: t("chart.target_line"),
            data: labels.map((_, i) => paceTarget(this.targetMinor, i + 1, length)),
            borderColor: p.muted,
            borderDash: [6, 4],
            pointRadius: 0,
            borderWidth: 1.5,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 8, autoSkip: true } },
          y: { beginAtZero: true, grid: { color: p.grid }, ticks: { callback: money, precision: 0 }, suggestedMax: 100 },
        },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12 } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y ?? 0)}` } },
        },
      },
    };
  }
}
define("pb-pace-chart", PbPaceChart);
