import { css, html, nothing } from "lit";
import { api } from "../api";
import { todayIso } from "../dates";
import { t } from "../i18n";
import { UI_DELETE } from "../icons";
import "../components/pb-backup-import";
import "../components/pb-icon";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Currency, Direction } from "../types";
import { define } from "../define";

interface BudgetDraft {
  name: string;
  percent: string;
  direction: Direction;
}

/** v1.2 P2: the suggested Savings budget is positive (reach at least). */
const DEFAULT_BUDGETS: BudgetDraft[] = [
  { name: "Needs", percent: "50", direction: "negative" },
  { name: "Wants", percent: "30", direction: "negative" },
  { name: "Savings", percent: "20", direction: "positive" },
];

/** First-run wizard: currency (K1) → first period (P6) → budgets (B1). */
export class PageSetup extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _step: { state: true },
    _currencies: { state: true },
    _currency: { state: true },
    _start: { state: true },
    _periodName: { state: true },
    _budgets: { state: true },
    _error: { state: true },
    _busy: { state: true },
  };
  declare _step: number;
  declare _currencies: Currency[];
  declare _currency: string;
  declare _start: string;
  declare _periodName: string;
  declare _budgets: BudgetDraft[];
  declare _error: string;
  declare _busy: boolean;

  constructor() {
    super();
    this._step = 0;
    this._currencies = [];
    this._currency = "EUR";
    this._start = todayIso();
    this._periodName = "";
    this._budgets = DEFAULT_BUDGETS.map((b) => ({ ...b }));
    this._error = "";
    this._busy = false;
  }

  static override styles = [
    shared,
    css`
      .budget {
        display: grid;
        grid-template-columns: 1fr 72px 112px 40px;
        gap: 8px;
        align-items: center;
        margin-bottom: 8px;
      }
    `,
  ];

  protected async load() {
    this._currencies = (await api.get<{ items: Currency[] }>("currencies")).items;
  }

  /** Sum of percents in hundredths, without floats. */
  private totalHundredths(): number | null {
    let total = 0;
    for (const b of this._budgets) {
      const m = /^(\d{1,3})(?:\.(\d{1,2}))?$/.exec(b.percent.trim());
      if (!m) return null;
      total += Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
    }
    return total;
  }

  private updateBudget(index: number, changes: Partial<BudgetDraft>) {
    this._budgets = this._budgets.map((b, i) => (i === index ? { ...b, ...changes } : b));
  }

  private async finish() {
    this._busy = true;
    this._error = "";
    try {
      await api.post("setup", {
        currency: this._currency,
        first_period: { start_date: this._start, name: this._periodName.trim() || null },
        budgets: this._budgets
          .filter((b) => b.name.trim())
          .map((b, i) => ({ name: b.name.trim(), percent: b.percent.trim(), direction: b.direction, sort_order: i })),
      });
      this.changed();
    } catch (err) {
      this._error = err instanceof Error ? err.message : t("error.generic");
    } finally {
      this._busy = false;
    }
  }

  private renderStep() {
    if (this._step === 0) {
      return html`<h2>${t("setup.step_currency")}</h2>
        <label class="field">
          <select aria-label=${t("settings.currency")} @change=${(e: Event) => (this._currency = (e.target as HTMLSelectElement).value)}>
            ${this._currencies.map((c) => html`<option value=${c.code} ?selected=${c.code === this._currency}>${c.code}</option>`)}
          </select>
        </label>
        <div class="actions"><button class="primary" @click=${() => (this._step = 1)}>${t("setup.next")}</button></div>`;
    }
    if (this._step === 1) {
      return html`<h2>${t("setup.step_period")}</h2>
        <p class="muted">${t("setup.period_hint")}</p>
        <label class="field">${t("periods.start_date")}<input type="date" required max=${todayIso()} .value=${this._start} @input=${(e: Event) => (this._start = (e.target as HTMLInputElement).value)} /></label>
        <label class="field">${t("common.name")} (${t("common.optional")})<input maxlength="100" .value=${this._periodName} @input=${(e: Event) => (this._periodName = (e.target as HTMLInputElement).value)} /></label>
        <div class="actions">
          <button @click=${() => (this._step = 0)}>${t("setup.back")}</button>
          <button class="primary" ?disabled=${!this._start} @click=${() => (this._step = 2)}>${t("setup.next")}</button>
        </div>`;
    }
    const total = this.totalHundredths();
    const valid = total !== null && total <= 10000;
    return html`<h2>${t("setup.step_budgets")}</h2>
      <p class="muted">${t("setup.budgets_hint")}</p>
      ${this._budgets.map(
        (b, i) => html`<div class="budget">
          <input aria-label=${t("common.name")} maxlength="100" .value=${b.name} @input=${(e: Event) => this.updateBudget(i, { name: (e.target as HTMLInputElement).value })} />
          <input aria-label=${t("budgets.percent")} inputmode="decimal" .value=${b.percent} @input=${(e: Event) => this.updateBudget(i, { percent: (e.target as HTMLInputElement).value })} />
          <select aria-label=${t("budgets.direction")} @change=${(e: Event) => this.updateBudget(i, { direction: (e.target as HTMLSelectElement).value as Direction })}>
            ${(["negative", "positive"] as const).map(
              (d) => html`<option value=${d} ?selected=${b.direction === d}>${t(`budgets.direction_${d}`)}</option>`,
            )}
          </select>
          <button class="icon" aria-label=${t("common.delete")} @click=${() => (this._budgets = this._budgets.filter((_, j) => j !== i))}>
            <pb-icon .path=${UI_DELETE}></pb-icon>
          </button>
        </div>`,
      )}
      <p class=${valid ? "muted" : "error"}>
        ${total === null ? t("error.generic") : t("budgets.allocated", { percent: `${Math.trunc(total / 100)}.${String(total % 100).padStart(2, "0")}` })}
      </p>
      <div class="actions">
        <button @click=${() => (this._budgets = [...this._budgets, { name: "", percent: "0", direction: "negative" }])}>${t("setup.add_budget")}</button>
        <span class="spacer"></span>
        <button @click=${() => (this._step = 1)}>${t("setup.back")}</button>
        <button class="primary" ?disabled=${!valid || this._busy} @click=${this.finish}>${t("setup.finish")}</button>
      </div>
      <p class="muted">${t("budgets.direction_negative_help")}<br />${t("budgets.direction_positive_help")}</p>
      ${this._error ? html`<p class="error">${this._error}</p>` : nothing}`;
  }

  override render() {
    return html`<h1>${t("setup.title")}</h1>
      <div class="card">${this.renderStep()}</div>
      ${this._step === 0
        ? html`<div class="card">
            <p class="muted">${t("setup.restore_hint")}</p>
            <pb-backup-import></pb-backup-import>
          </div>`
        : nothing}`;
  }
}
define("page-setup", PageSetup);
