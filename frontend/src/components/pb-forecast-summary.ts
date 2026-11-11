import { LitElement, css, html, nothing } from "lit";
import "./charts/pb-forecast-chart";
import { formatDate } from "../dates";
import { t } from "../i18n";
import { type CurrencyInfo, formatMoney } from "../money";
import { shared } from "../styles";
import type { Forecast } from "../types";
import { define } from "../define";

/** v1.3: projected balance, safe per day and expected payday, with the forecast chart. */
export class PbForecastSummary extends LitElement {
  static override properties = {
    forecast: { attribute: false },
    theme: {},
  };
  declare forecast: Forecast | null;
  declare theme: string;

  constructor() {
    super();
    this.forecast = null;
    this.theme = "";
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      .totals {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
        margin-bottom: 12px;
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
    `,
  ];

  override render() {
    const f = this.forecast;
    if (!f) return nothing;
    const currency: CurrencyInfo = { code: f.currency, minorUnit: f.minor_unit };
    const money = (minor: number) => formatMoney(minor, currency);
    return html`
      <div class="totals">
        <div class="total">
          <span class="muted">${t("forecast.balance")}</span>
          <strong class="amount ${f.balance_projected_minor < 0 ? "negative" : "positive"}">
            ${money(f.balance_projected_minor)}
          </strong>
        </div>
        <div class="total">
          <span class="muted">${t("forecast.safe")}</span>
          <strong class="amount">${money(f.safe_per_day_minor)}</strong>
        </div>
        <div class="total">
          <span class="muted">${t("forecast.payday")}</span>
          <strong>${formatDate(f.expected_payday)}</strong>
          <span class="muted">
            ${f.overdue ? t("forecast.overdue") : t("forecast.days_left", { days: f.days_left })}
          </span>
        </div>
      </div>
      <pb-forecast-chart .forecast=${f} .currency=${currency} .theme=${this.theme}></pb-forecast-chart>
    `;
  }
}
define("pb-forecast-summary", PbForecastSummary);
