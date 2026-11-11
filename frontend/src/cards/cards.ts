/** The four dashboard cards (§8), built on the shared M4 chart components. */
import { html } from "lit";
import "../components/charts/pb-category-chart";
import "../components/charts/pb-pace-chart";
import "../components/charts/pb-periods-chart";
import "../components/charts/pb-progress-chart";
import "../components/pb-forecast-summary";
import "../components/pb-upcoming-list";
import { t } from "../i18n";
import type { Breakdown, Daily, Forecast, HistoryItem, Summary } from "../types";
import { PaydayCard, matchesBudget } from "./card-base";

/** Per budget: target vs spent bars, plus unallocated. Options: period, budget, forecast, title. */
export class ProgressCard extends PaydayCard {
  static override properties = {
    ...PaydayCard.properties,
    _summary: { state: true },
    _forecast: { state: true },
  };
  declare _summary: Summary | null;
  declare _forecast: Forecast | null;
  protected readonly options = ["period", "budget", "forecast", "title"] as const;
  protected readonly rows = 6;

  protected defaultTitle() {
    return t("chart.progress");
  }

  protected async fetchData() {
    // v1.3 (P3): the projected marker is for the current period only.
    const withForecast = this._config.forecast === true && this.period() === "current";
    const [summary, forecast] = await Promise.all([
      this.ws<Summary>("summary", { period: this.period() }),
      withForecast ? this.ws<Forecast>("forecast") : Promise.resolve(null),
    ]);
    this._summary = summary;
    this._forecast = forecast;
  }

  protected renderContent() {
    const s = this._summary;
    if (!s) return html``;
    const budget = this._config.budget;
    const shown = { ...s, budgets: s.budgets.filter((b) => matchesBudget(budget, b.budget_id, b.name)) };
    return html`<pb-progress-chart
      .summary=${shown}
      .showUnallocated=${budget === undefined}
      .forecast=${this._forecast}
    ></pb-progress-chart>`;
  }
}

/** Income vs expenses for the last N periods. Options: limit, stacked, title. */
export class PeriodsCard extends PaydayCard {
  static override properties = {
    ...PaydayCard.properties,
    _history: { state: true },
    _summary: { state: true },
  };
  declare _history: HistoryItem[];
  declare _summary: Summary | null;
  protected readonly options = ["limit", "stacked", "title"] as const;
  protected readonly rows = 5;

  protected defaultTitle() {
    return t("chart.periods");
  }

  protected async fetchData() {
    const [history, summary] = await Promise.all([
      this.ws<{ items: HistoryItem[] }>("history", { limit: this._config.limit ?? 12 }),
      this.ws<Summary>("summary", { period: "current" }),
    ]);
    this._history = history.items;
    this._summary = summary;
  }

  protected renderContent() {
    if (!this._summary) return html``;
    return html`<pb-periods-chart
      .items=${this._history}
      .currency=${this.currencyOf(this._summary)}
      .stacked=${this._config.stacked ?? false}
      .theme=${this._theme}
    ></pb-periods-chart>`;
  }
}

/** Donut by category for a period. Options: period, budget, title. */
export class CategoryCard extends PaydayCard {
  static override properties = {
    ...PaydayCard.properties,
    _breakdown: { state: true },
    _summary: { state: true },
  };
  declare _breakdown: Breakdown | null;
  declare _summary: Summary | null;
  protected readonly options = ["period", "budget", "title"] as const;
  protected readonly rows = 6;

  protected defaultTitle() {
    return t("chart.category");
  }

  protected async fetchData() {
    const [breakdown, summary] = await Promise.all([
      this.ws<Breakdown>("breakdown", { period: this.period(), budget: this._config.budget }),
      this.ws<Summary>("summary", { period: this.period() }),
    ]);
    this._breakdown = breakdown;
    this._summary = summary;
  }

  protected renderContent() {
    if (!this._summary) return html``;
    return html`<pb-category-chart
      .breakdown=${this._breakdown}
      .currency=${this.currencyOf(this._summary)}
      .theme=${this._theme}
    ></pb-category-chart>`;
  }
}

/** Cumulative daily spend vs a linear target line. Options: period, title. */
export class PaceCard extends PaydayCard {
  static override properties = {
    ...PaydayCard.properties,
    _daily: { state: true },
    _summary: { state: true },
  };
  declare _daily: Daily | null;
  declare _summary: Summary | null;
  protected readonly options = ["period", "title"] as const;
  protected readonly rows = 5;

  protected defaultTitle() {
    return t("chart.pace");
  }

  protected async fetchData() {
    const [daily, summary] = await Promise.all([
      this.ws<Daily>("daily", { period: this.period() }),
      this.ws<Summary>("summary", { period: this.period() }),
    ]);
    this._daily = daily;
    this._summary = summary;
  }

  protected renderContent() {
    const s = this._summary;
    if (!s) return html``;
    // Same target as the add-on dashboard: total of budget targets (income - unallocated).
    return html`<pb-pace-chart
      .daily=${this._daily}
      .targetMinor=${s.income_minor - s.unallocated.amount_minor}
      .currency=${this.currencyOf(s)}
      .theme=${this._theme}
    ></pb-pace-chart>`;
  }
}

/** v1.3 §7: projected balance, safe per day, expected payday and the balance chart. Options: title. */
export class ForecastCard extends PaydayCard {
  static override properties = { ...PaydayCard.properties, _forecast: { state: true } };
  declare _forecast: Forecast | null;
  protected readonly options = ["title"] as const;
  protected readonly rows = 6;

  protected defaultTitle() {
    return t("forecast.title");
  }

  protected async fetchData() {
    this._forecast = await this.ws<Forecast>("forecast");
  }

  protected renderContent() {
    return html`<pb-forecast-summary .forecast=${this._forecast} .theme=${this._theme}></pb-forecast-summary>`;
  }
}

/** v1.3 §7: what is expected before the payday, due reminders first. Options: limit, title. */
export class UpcomingCard extends PaydayCard {
  static override properties = { ...PaydayCard.properties, _forecast: { state: true } };
  declare _forecast: Forecast | null;
  protected readonly options = ["limit", "title"] as const;
  protected readonly rows = 4;

  protected defaultTitle() {
    return t("upcoming.title");
  }

  protected async fetchData() {
    this._forecast = await this.ws<Forecast>("forecast");
  }

  protected renderContent() {
    return html`<pb-upcoming-list .forecast=${this._forecast} .limit=${this._config.limit ?? 0}></pb-upcoming-list>`;
  }
}
