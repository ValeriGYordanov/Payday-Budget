import { css, html, nothing } from "lit";
import { ApiError, api } from "../api";
import { confirmAction } from "../components/pb-dialog";
import "../components/pb-dialog";
import "../components/pb-icon";
import "../components/pb-reminder-rules";
import { formatDate, todayIso } from "../dates";
import { kindLabel, t } from "../i18n";
import { UI_DELETE, UI_EDIT } from "../icons";
import { type CurrencyInfo, amountInputValue, formatMoney, parseAmount } from "../money";
import { PageElement, errorMessage } from "../page";
import { shared } from "../styles";
import type { BudgetList, Category, Frequency, Kind, RecurringRule } from "../types";
import { define } from "../define";

interface Draft {
  id: number | null;
  kind: Kind;
  amount: string;
  categoryId: string;
  budgetId: string;
  description: string;
  tags: string;
  frequency: Frequency;
  interval: string;
  anchorDate: string;
  endDate: string;
  active: boolean;
}

const UNIT = { weekly: "recurring.weekly", monthly: "recurring.monthly", yearly: "recurring.yearly" } as const;

/** Recurring transactions (§5.5): list, create, edit, pause, delete. */
export class PageRecurring extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _items: { state: true },
    _categories: { state: true },
    _budgets: { state: true },
    _draft: { state: true },
    _error: { state: true },
  };
  declare _items: RecurringRule[];
  declare _categories: Category[];
  declare _budgets: BudgetList["items"];
  declare _draft: Draft | null;
  declare _error: string;

  constructor() {
    super();
    this._items = [];
    this._categories = [];
    this._budgets = [];
    this._draft = null;
    this._error = "";
  }

  static override styles = [
    shared,
    css`
      .two {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0 12px;
      }
    `,
  ];

  protected async load() {
    const [rules, categories, budgets] = await Promise.all([
      api.get<{ items: RecurringRule[] }>("recurring"),
      api.get<{ items: Category[] }>("categories"),
      api.get<BudgetList>("budgets"),
    ]);
    this._items = rules.items;
    this._categories = categories.items;
    this._budgets = budgets.items;
  }

  private open(rule: RecurringRule | null) {
    this._error = "";
    this._draft = rule
      ? {
          id: rule.id,
          kind: rule.kind,
          amount: amountInputValue(rule.amount_minor, this.settings.minor_unit),
          categoryId: String(rule.category_id),
          budgetId: rule.budget_id === null ? "" : String(rule.budget_id),
          description: rule.description ?? "",
          tags: rule.tags.join(", "),
          frequency: rule.frequency,
          interval: String(rule.interval),
          anchorDate: rule.anchor_date,
          endDate: rule.end_date ?? "",
          active: rule.active,
        }
      : {
          id: null,
          kind: "expense",
          amount: "",
          categoryId: "",
          budgetId: "",
          description: "",
          tags: "",
          frequency: "monthly",
          interval: "1",
          anchorDate: todayIso(),
          endDate: "",
          active: true,
        };
  }

  private patch(changes: Partial<Draft>) {
    if (this._draft) this._draft = { ...this._draft, ...changes };
  }

  private async save(e: Event) {
    e.preventDefault();
    const d = this._draft;
    if (!d) return;
    const amount = parseAmount(d.amount, this.settings.minor_unit);
    if (amount === null || amount <= 0) {
      this._error = t("tx.amount_invalid", { digits: this.settings.minor_unit });
      return;
    }
    const body = {
      kind: d.kind,
      amount_minor: amount,
      category_id: d.categoryId ? Number(d.categoryId) : null,
      budget_id: d.kind === "expense" && d.budgetId ? Number(d.budgetId) : null,
      description: d.description.trim() || null,
      tags: d.tags.split(",").map((s) => s.trim()).filter(Boolean),
      frequency: d.frequency,
      interval: Number(d.interval),
      anchor_date: d.anchorDate || null,
      end_date: d.endDate || null,
      active: d.active,
    };
    try {
      if (d.id === null) await api.post("recurring", body);
      else await api.patch(`recurring/${d.id}`, body);
      this._draft = null;
      this.changed();
    } catch (err) {
      this._error = err instanceof ApiError ? err.message : errorMessage(err);
    }
  }

  private async deleteItem(rule: RecurringRule) {
    const name = rule.description ?? rule.category_name ?? "";
    if (await confirmAction(t("common.confirm_delete", { name }), t("common.delete"))) {
      await this.write(() => api.delete(`recurring/${rule.id}`));
    }
  }

  private renderForm(d: Draft) {
    const original = this._items.find((r) => r.id === d.id);
    const categories = this._categories.filter(
      (c) => c.kind === d.kind && (!c.archived || c.id === original?.category_id),
    );
    const budgets = this._budgets.filter((b) => !b.archived || b.id === original?.budget_id);
    const value = (e: Event) => (e.target as HTMLInputElement).value;
    return html`<form @submit=${this.save}>
      <div class="field">
        <div class="segmented" role="group" aria-label=${t("tx.kind")}>
          ${(["expense", "income"] as Kind[]).map(
            (kind) => html`<button type="button" aria-pressed=${d.kind === kind} @click=${() => d.kind !== kind && this.patch({ kind, categoryId: "", budgetId: "" })}>
              ${kindLabel(kind)}
            </button>`,
          )}
        </div>
      </div>
      <br />
      <label class="field">${t("tx.amount")}<input required inputmode="decimal" .value=${d.amount} @input=${(e: Event) => this.patch({ amount: value(e) })} /></label>
      <div class="two">
        <label class="field">
          ${t("tx.category")}
          <select required @change=${(e: Event) => this.patch({ categoryId: value(e) })}>
            <option value="" ?selected=${!d.categoryId}>${t("tx.choose")}</option>
            ${categories.map((c) => html`<option value=${c.id} ?selected=${String(c.id) === d.categoryId}>${c.name}</option>`)}
          </select>
        </label>
        ${d.kind === "expense"
          ? html`<label class="field">
              ${t("tx.budget")}
              <select required @change=${(e: Event) => this.patch({ budgetId: value(e) })}>
                <option value="" ?selected=${!d.budgetId}>${t("tx.choose")}</option>
                ${budgets.map((b) => html`<option value=${b.id} ?selected=${String(b.id) === d.budgetId}>${b.name}</option>`)}
              </select>
            </label>`
          : nothing}
      </div>
      <div class="two">
        <label class="field">
          ${t("recurring.frequency")}
          <select @change=${(e: Event) => this.patch({ frequency: value(e) as Frequency })}>
            ${(["weekly", "monthly", "yearly"] as Frequency[]).map(
              (f) => html`<option value=${f} ?selected=${d.frequency === f}>${t(UNIT[f])}</option>`,
            )}
          </select>
        </label>
        <label class="field">${t("recurring.every")}<input type="number" min="1" step="1" required .value=${d.interval} @input=${(e: Event) => this.patch({ interval: value(e) })} /></label>
      </div>
      <div class="two">
        <label class="field">${t("recurring.anchor")}<input type="date" required .value=${d.anchorDate} @input=${(e: Event) => this.patch({ anchorDate: value(e) })} /></label>
        <label class="field">${t("recurring.end")} (${t("common.optional")})<input type="date" .value=${d.endDate} @input=${(e: Event) => this.patch({ endDate: value(e) })} /></label>
      </div>
      <label class="field">${t("tx.description")} (${t("common.optional")})<input maxlength="500" .value=${d.description} @input=${(e: Event) => this.patch({ description: value(e) })} /></label>
      <label class="field">${t("tx.tags")} (${t("tx.tags_hint")})<input .value=${d.tags} @input=${(e: Event) => this.patch({ tags: value(e) })} /></label>
      <label class="row"><input type="checkbox" .checked=${d.active} @change=${(e: Event) => this.patch({ active: (e.target as HTMLInputElement).checked })} />${t("recurring.active")}</label>
      ${this._error ? html`<p class="error">${this._error}</p>` : nothing}
      <div class="actions">
        <button type="button" @click=${() => (this._draft = null)}>${t("common.cancel")}</button>
        <button class="primary" type="submit">${t("common.save")}</button>
      </div>
    </form>`;
  }

  override render() {
    const currency: CurrencyInfo = { code: this.settings.currency, minorUnit: this.settings.minor_unit };
    return html`
      <div class="card">
        ${this._items.length === 0
          ? html`<p class="muted">${t("common.empty")}</p>`
          : html`<ul class="list">
              ${this._items.map(
                (r) => html`<li>
                  <div class="grow">
                    <div class="row">
                      <strong class="ellipsis">${r.description ?? r.category_name}</strong>
                      ${r.active ? nothing : html`<span class="badge">${t("recurring.paused")}</span>`}
                    </div>
                    <div class="muted">
                      ${t("recurring.summary", { interval: r.interval, unit: t(UNIT[r.frequency]), date: formatDate(r.anchor_date) })}
                      ${r.budget_name ? ` · ${r.budget_name}` : ""}
                    </div>
                    ${r.last_generated_date
                      ? html`<div class="muted">${t("recurring.last", { date: formatDate(r.last_generated_date) })}</div>`
                      : nothing}
                  </div>
                  <span class="amount ${r.kind === "income" ? "positive" : ""}">${formatMoney(r.amount_minor, currency)}</span>
                  <button class="icon" aria-label=${t("common.edit")} @click=${() => this.open(r)}><pb-icon .path=${UI_EDIT}></pb-icon></button>
                  <button class="icon" aria-label=${t("common.delete")} @click=${() => this.deleteItem(r)}><pb-icon .path=${UI_DELETE}></pb-icon></button>
                </li>`,
              )}
            </ul>`}
        <div class="actions"><button class="primary" @click=${() => this.open(null)}>${t("recurring.new")}</button></div>
      </div>
      <pb-dialog
        .heading=${this._draft?.id ? t("recurring.edit") : t("recurring.new")}
        .open=${this._draft !== null}
        @closed=${() => (this._draft = null)}
      >
        ${this._draft ? this.renderForm(this._draft) : nothing}
      </pb-dialog>
      <pb-reminder-rules .settings=${this.settings} .revision=${this.revision}></pb-reminder-rules>
    `;
  }
}
define("page-recurring", PageRecurring);
