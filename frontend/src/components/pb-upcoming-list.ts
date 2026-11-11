import { LitElement, css, html, nothing } from "lit";
import { formatDate } from "../dates";
import { t } from "../i18n";
import { type CurrencyInfo, formatMoney } from "../money";
import { shared } from "../styles";
import type { Forecast } from "../types";
import { define } from "../define";

/** v1.3 F9: recurring transactions and reminders expected before the payday, due ones first. */
export class PbUpcomingList extends LitElement {
  static override properties = {
    forecast: { attribute: false },
    limit: { type: Number },
  };
  declare forecast: Forecast | null;
  declare limit: number;

  constructor() {
    super();
    this.forecast = null;
    this.limit = 0;
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
    `,
  ];

  override render() {
    const f = this.forecast;
    if (!f) return nothing;
    const items = this.limit > 0 ? f.upcoming.slice(0, this.limit) : f.upcoming;
    if (items.length === 0) return html`<p class="muted">${t("upcoming.none")}</p>`;
    const currency: CurrencyInfo = { code: f.currency, minorUnit: f.minor_unit };
    return html`<ul class="list">
      ${items.map(
        (i) => html`<li>
          <div class="grow">
            <div class="row">
              <strong class="ellipsis">${i.name}</strong>
              ${i.due ? html`<span class="badge">${t("upcoming.due")}</span>` : nothing}
            </div>
            <div class="muted">${formatDate(i.date)}${i.budget_name ? ` · ${i.budget_name}` : ""}</div>
          </div>
          <span class="amount ${i.kind === "income" ? "positive" : ""}">
            ${i.amount_minor === null
              ? "?"
              : `${i.estimated ? "≈ " : ""}${i.kind === "income" ? "+" : "−"}${formatMoney(i.amount_minor, currency)}`}
          </span>
        </li>`,
      )}
    </ul>`;
  }
}
define("pb-upcoming-list", PbUpcomingList);
