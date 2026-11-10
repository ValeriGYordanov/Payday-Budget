import { LitElement, css, html, nothing } from "lit";
import { t } from "../../i18n";
import { type CurrencyInfo, formatMoney } from "../../money";
import { shared } from "../../styles";
import type { Summary } from "../../types";
import { define } from "../../define";

/** §8 progress: per budget target vs spent bars, plus unallocated. */
export class PbProgressChart extends LitElement {
  static override properties = {
    summary: { attribute: false },
    showUnallocated: { type: Boolean },
  };
  declare summary: Summary | null;
  declare showUnallocated: boolean;

  constructor() {
    super();
    this.summary = null;
    this.showUnallocated = true;
  }

  static override styles = [
    shared,
    css`
      .budget {
        margin-bottom: 14px;
      }
      .top {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 4px;
      }
      .track {
        height: 10px;
        border-radius: 5px;
        background: var(--pb-track);
        overflow: hidden;
      }
      .fill {
        height: 100%;
        border-radius: 5px;
        background: var(--pb-primary);
      }
      .fill.over {
        background: var(--pb-negative);
      }
      .fill.below {
        background: var(--pb-warning);
      }
      .fill.met {
        background: var(--pb-positive);
      }
      .warning {
        color: var(--pb-warning);
      }
      .fill.unallocated {
        background: var(--pb-text-muted);
      }
      .sub {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        margin-top: 2px;
      }
    `,
  ];

  override render() {
    const s = this.summary;
    if (!s) return nothing;
    const currency: CurrencyInfo = { code: s.currency, minorUnit: s.minor_unit };
    const money = (minor: number) => formatMoney(minor, currency);
    return html`
      ${s.budgets.map((b) => {
        // Bar width is presentation only; amounts stay integer minor units.
        const used = b.percent_used === null ? (b.spent_minor > 0 ? 100 : 0) : Number(b.percent_used);
        // BD3: a positive budget counts up to its target; above it is good.
        const positive = b.direction === "positive";
        const left =
          b.remaining_minor >= 0
            ? t(positive ? "chart.to_go" : "chart.remaining", { amount: money(b.remaining_minor) })
            : t(positive ? "chart.above" : "chart.over", { amount: money(-b.remaining_minor) });
        const leftClass = b.status === "over" ? "negative" : b.status === "below" ? "warning" : b.status === "met" ? "positive" : "";
        return html`<div class="budget">
          <div class="top">
            <strong class="ellipsis">${b.name}</strong>
            <span class="amount">${money(b.spent_minor)} / ${money(b.target_minor)}</span>
          </div>
          <div class="track" role="progressbar" aria-label=${b.name} aria-valuenow=${Math.round(used)}>
            <div class="fill ${b.status === "ok" ? "" : b.status}" style="width:${Math.min(used, 100)}%"></div>
          </div>
          <div class="sub muted">
            <span>${b.percent}%${b.percent_used !== null ? ` · ${t("chart.used", { percent: b.percent_used })}` : ""}</span>
            <span class=${leftClass}>${left}</span>
          </div>
        </div>`;
      })}
      ${this.showUnallocated ? this.renderUnallocated(s, money) : nothing}
    `;
  }

  private renderUnallocated(s: Summary, money: (minor: number) => string) {
    return html`
      <div class="budget">
        <div class="top">
          <strong>${t("dash.unallocated")}</strong>
          <span class="amount">${money(s.unallocated.amount_minor)}</span>
        </div>
        <div class="track">
          <div class="fill unallocated" style="width:${Math.max(0, Math.min(Number(s.unallocated.percent), 100))}%"></div>
        </div>
        <div class="sub muted"><span>${s.unallocated.percent}%</span></div>
      </div>
    `;
  }
}
define("pb-progress-chart", PbProgressChart);
