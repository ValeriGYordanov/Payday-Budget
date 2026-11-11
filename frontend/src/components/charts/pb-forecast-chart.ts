import type { ChartConfiguration } from "chart.js";
import { formatDate } from "../../dates";
import { t } from "../../i18n";
import type { CurrencyInfo } from "../../money";
import type { Forecast } from "../../types";
import { ChartElement, type Palette, moneyTick } from "./chart-base";
import { define } from "../../define";

/**
 * v1.3 §7: running balance from the period start to today (solid) and projected to the
 * day before the expected payday (dashed); days with known items are marked.
 */
export class PbForecastChart extends ChartElement {
  static override properties = {
    ...ChartElement.properties,
    forecast: { attribute: false },
    currency: { attribute: false },
  };
  declare forecast: Forecast | null;
  declare currency: CurrencyInfo | null;

  constructor() {
    super();
    this.forecast = null;
    this.currency = null;
  }

  protected chartConfig(p: Palette): ChartConfiguration | null {
    const f = this.forecast;
    if (!f || !this.currency || f.series.length === 0) return null;
    const money = moneyTick(this.currency);
    const labels = f.series.map((point) => formatDate(point.date));
    const lastActual = f.series.findLastIndex((point) => !point.projected);
    const actual = f.series.map((point, i) => (i <= lastActual ? point.balance_minor : null));
    // The projection starts at today's balance so the two lines join.
    const projected = f.series.map((point, i) => (i >= lastActual ? point.balance_minor : null));
    return {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: t("forecast.actual"),
            data: actual,
            borderColor: p.primary,
            backgroundColor: p.primary,
            pointRadius: 0,
            borderWidth: 2,
            fill: false,
          },
          {
            label: t("forecast.projected"),
            data: projected,
            borderColor: p.muted,
            backgroundColor: p.muted,
            borderDash: [6, 4],
            pointRadius: f.series.map((point) => (point.projected && point.items > 0 ? 3 : 0)),
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
          y: { grid: { color: p.grid }, ticks: { callback: money, precision: 0 } },
        },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12 } },
          tooltip: {
            filter: (item) => item.parsed.y !== null,
            callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y ?? 0)}` },
          },
        },
      },
    };
  }
}
define("pb-forecast-chart", PbForecastChart);
