import { css, html, nothing } from "lit";
import { api, query } from "../api";
import "../components/charts/pb-category-chart";
import "../components/charts/pb-pace-chart";
import "../components/charts/pb-periods-chart";
import "../components/charts/pb-progress-chart";
import { formatDate } from "../dates";
import { t } from "../i18n";
import { type CurrencyInfo, formatMoney } from "../money";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Breakdown, Daily, HistoryItem, Period, Summary } from "../types";

const HISTORY_LIMIT = 12;

/** Dashboard: a period (current by default) with all §8 charts. */
export class PageDashboard extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _periods: { state: true },
    _periodRef: { state: true },
    _summary: { state: true },
    _daily: { state: true },
    _breakdown: { state: true },
    _history: { state: true },
    _breakdownBudget: { state: true },
    _stacked: { state: true },
  };
  declare _periods: Period[];
  declare _periodRef: string;
  declare _summary: Summary | null;
  declare _daily: Daily | null;
  declare _breakdown: Breakdown | null;
  declare _history: HistoryItem[];
  declare _breakdownBudget: string;
  declare _stacked: boolean;

  constructor() {
    super();
    this._periods = [];
    this._periodRef = "current";
    this._summary = null;
    this._daily = null;
    this._breakdown = null;
    this._history = [];
    this._breakdownBudget = "";
    this._stacked = false;
  }

  static override styles = [
    shared,
    css`
      .totals {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
      }
      .total {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .total strong {
        font-size: 1.05rem;
      }
      @media (max-width: 400px) {
        .totals {
          grid-template-columns: 1fr;
        }
        .total {
          flex-direction: row;
          justify-content: space-between;
        }
      }
      .grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: 0 16px;
      }
      @media (min-width: 760px) {
        .grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
      }
      .card-head {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 12px;
      }
      .card-head h2 {
        margin: 0;
        flex: 1;
      }
      .card-head select {
        width: auto;
        max-width: 100%;
      }
    `,
  ];

  protected async load() {
    const periods = await api.get<{ items: Period[] }>("periods");
    this._periods = periods.items;
    if (periods.items.length === 0) return;
    if (this._periodRef !== "current" && !periods.items.some((p) => String(p.id) === this._periodRef)) {
      this._periodRef = "current";
    }
    const ref = this._periodRef;
    const [summary, daily, breakdown, history] = await Promise.all([
      api.get<Summary>(`summary${query({ period: ref })}`),
      api.get<Daily>(`daily${query({ period: ref })}`),
      api.get<Breakdown>(`breakdown${query({ period: ref, budget: this._breakdownBudget })}`),
      api.get<{ items: HistoryItem[] }>(`periods/history${query({ limit: HISTORY_LIMIT })}`),
    ]);
    this._summary = summary;
    this._daily = daily;
    this._breakdown = breakdown;
    this._history = history.items;
  }

  private selectPeriod(ref: string) {
    this._periodRef = ref;
    this._breakdownBudget = "";
    void this.reload();
  }

  private async selectBreakdownBudget(budget: string) {
    this._breakdownBudget = budget;
    try {
      this._breakdown = await api.get<Breakdown>(
        `breakdown${query({ period: this._periodRef, budget })}`,
      );
    } catch (err) {
      this.fail(err);
    }
  }

  override render() {
    const s = this._summary;
    if (this._periods.length === 0) return html`<p class="muted">${t("dash.no_period")}</p>`;
    if (!s) return html`<p class="muted">${t("common.loading")}</p>`;
    const currency: CurrencyInfo = { code: s.currency, minorUnit: s.minor_unit };
    const money = (minor: number) => formatMoney(minor, currency);
    const p = s.period;
    // Pace line ends at the total of all budget targets (= income - unallocated).
    const targetTotal = s.income_minor - s.unallocated.amount_minor;
    return html`
      <div class="card">
        <label class="field">
          ${t("dash.period")}
          <select .value=${this._periodRef} @change=${(e: Event) => this.selectPeriod((e.target as HTMLSelectElement).value)}>
            <option value="current" ?selected=${this._periodRef === "current"}>${t("filter.current")}</option>
            ${this._periods.map(
              (period) =>
                html`<option value=${period.id} ?selected=${String(period.id) === this._periodRef}>
                  ${period.name}
                </option>`,
            )}
          </select>
        </label>
        <p class="muted">
          ${formatDate(p.start_date)} – ${p.end_date ? formatDate(p.end_date) : t("periods.open")} ·
          ${t("dash.days", { days: p.days_elapsed })}
        </p>
        <div class="totals">
          <div class="total">
            <span class="muted">${t("dash.income")}</span>
            <strong class="amount positive">${money(s.income_minor)}</strong>
          </div>
          <div class="total">
            <span class="muted">${t("dash.expenses")}</span>
            <strong class="amount negative">${money(s.expenses_minor)}</strong>
          </div>
          <div class="total">
            <span class="muted">${t("dash.balance")}</span>
            <strong class="amount">${money(s.balance_minor)}</strong>
          </div>
        </div>
      </div>
      <div class="grid">
        <div class="card">
          <h2>${t("chart.progress")}</h2>
          <pb-progress-chart .summary=${s}></pb-progress-chart>
        </div>
        <div class="card">
          <h2>${t("chart.pace")}</h2>
          <pb-pace-chart .daily=${this._daily} .targetMinor=${targetTotal} .currency=${currency}></pb-pace-chart>
        </div>
        <div class="card">
          <div class="card-head">
            <h2>${t("chart.category")}</h2>
            <select
              aria-label=${t("filter.budget")}
              .value=${this._breakdownBudget}
              @change=${(e: Event) => this.selectBreakdownBudget((e.target as HTMLSelectElement).value)}
            >
              <option value="" ?selected=${!this._breakdownBudget}>${t("chart.all_budgets")}</option>
              ${s.budgets.map(
                (b) =>
                  html`<option value=${b.budget_id} ?selected=${String(b.budget_id) === this._breakdownBudget}>
                    ${b.name}
                  </option>`,
              )}
            </select>
          </div>
          <pb-category-chart .breakdown=${this._breakdown} .currency=${currency}></pb-category-chart>
        </div>
        <div class="card">
          <div class="card-head">
            <h2>${t("chart.periods")}</h2>
            <label class="row muted">
              <input
                type="checkbox"
                .checked=${this._stacked}
                @change=${(e: Event) => (this._stacked = (e.target as HTMLInputElement).checked)}
              />
              ${t("chart.periods_stack")}
            </label>
          </div>
          ${this._history.length
            ? html`<pb-periods-chart
                .items=${this._history}
                .currency=${currency}
                .stacked=${this._stacked}
              ></pb-periods-chart>`
            : nothing}
        </div>
      </div>
    `;
  }
}
customElements.define("page-dashboard", PageDashboard);
