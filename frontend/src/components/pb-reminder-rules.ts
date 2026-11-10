import { css, html, nothing } from "lit";
import { ApiError, api } from "../api";
import { confirmAction } from "./pb-dialog";
import "./pb-dialog";
import "./pb-icon";
import "./pb-reminders";
import { formatDate, todayIso } from "../dates";
import { kindLabel, t } from "../i18n";
import { UI_DELETE, UI_EDIT } from "../icons";
import { type CurrencyInfo, amountInputValue, formatMoney, parseAmount } from "../money";
import { PageElement, errorMessage } from "../page";
import { shared } from "../styles";
import type { BudgetList, Category, Frequency, Kind, Reminder, ReminderOccurrence } from "../types";
import { define } from "../define";

interface Draft {
  id: number | null;
  name: string;
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

/** Reminders section of the Recurring tab (v1.2 §4.3): due ones, then list / add / edit / delete. */
export class PbReminderRules extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _items: { state: true },
    _open: { state: true },
    _categories: { state: true },
    _budgets: { state: true },
    _draft: { state: true },
    _error: { state: true },
  };
  declare _items: Reminder[];
  declare _open: ReminderOccurrence[];
  declare _categories: Category[];
  declare _budgets: BudgetList["items"];
  declare _draft: Draft | null;
  declare _error: string;

  constructor() {
    super();
    this._items = [];
    this._open = [];
    this._categories = [];
    this._budgets = [];
    this._draft = null;
    this._error = "";
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      .two {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0 12px;
      }
    `,
  ];

  protected async load() {
    const [reminders, open, categories, budgets] = await Promise.all([
      api.get<{ items: Reminder[] }>("reminders"),
      api.get<{ items: ReminderOccurrence[] }>("reminders/occurrences?status=open"),
      api.get<{ items: Category[] }>("categories"),
      api.get<BudgetList>("budgets"),
    ]);
    this._items = reminders.items;
    this._open = open.items;
    this._categories = categories.items;
    this._budgets = budgets.items;
  }

  private edit(reminder: Reminder | null) {
    this._error = "";
    this._draft = reminder
      ? {
          id: reminder.id,
          name: reminder.name,
          kind: reminder.kind,
          amount:
            reminder.amount_minor === null ? "" : amountInputValue(reminder.amount_minor, this.settings.minor_unit),
          categoryId: reminder.category_id === null ? "" : String(reminder.category_id),
          budgetId: reminder.budget_id === null ? "" : String(reminder.budget_id),
          description: reminder.description ?? "",
          tags: reminder.tags.join(", "),
          frequency: reminder.frequency,
          interval: String(reminder.interval),
          anchorDate: reminder.anchor_date,
          endDate: reminder.end_date ?? "",
          active: reminder.active,
        }
      : {
          id: null,
          name: "",
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
    let amount: number | null = null;
    if (d.amount.trim()) {
      amount = parseAmount(d.amount, this.settings.minor_unit);
      if (amount === null || amount <= 0) {
        this._error = t("tx.amount_invalid", { digits: this.settings.minor_unit });
        return;
      }
    }
    const body = {
      name: d.name.trim(),
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
      if (d.id === null) await api.post("reminders", body);
      else await api.patch(`reminders/${d.id}`, body);
      this._draft = null;
      this.changed();
    } catch (err) {
      this._error = err instanceof ApiError ? err.message : errorMessage(err);
    }
  }

  private async deleteItem(reminder: Reminder) {
    if (await confirmAction(t("common.confirm_delete", { name: reminder.name }), t("common.delete"))) {
      await this.write(() => api.delete(`reminders/${reminder.id}`));
    }
  }

  private renderForm(d: Draft) {
    const original = this._items.find((r) => r.id === d.id);
    const categories = this._categories.filter(
      (c) => c.kind === d.kind && (!c.archived || c.id === original?.category_id),
    );
    const budgets = this._budgets.filter((b) => !b.archived || b.id === original?.budget_id);
    const value = (e: Event) => (e.target as HTMLInputElement).value;
    const optional = `(${t("common.optional")})`;
    return html`<form @submit=${this.save}>
      <label class="field">${t("common.name")}<input required maxlength="100" .value=${d.name} @input=${(e: Event) => this.patch({ name: value(e) })} /></label>
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
      <label class="field">${t("tx.amount")} (${t("reminders.amount_hint")})<input inputmode="decimal" .value=${d.amount} @input=${(e: Event) => this.patch({ amount: value(e) })} /></label>
      <div class="two">
        <label class="field">
          ${t("tx.category")} ${optional}
          <select @change=${(e: Event) => this.patch({ categoryId: value(e) })}>
            <option value="" ?selected=${!d.categoryId}>${t("common.none")}</option>
            ${categories.map((c) => html`<option value=${c.id} ?selected=${String(c.id) === d.categoryId}>${c.name}</option>`)}
          </select>
        </label>
        ${d.kind === "expense"
          ? html`<label class="field">
              ${t("tx.budget")} ${optional}
              <select @change=${(e: Event) => this.patch({ budgetId: value(e) })}>
                <option value="" ?selected=${!d.budgetId}>${t("common.none")}</option>
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
        <label class="field">${t("recurring.end")} ${optional}<input type="date" .value=${d.endDate} @input=${(e: Event) => this.patch({ endDate: value(e) })} /></label>
      </div>
      <label class="field">${t("tx.description")} ${optional}<input maxlength="500" .value=${d.description} @input=${(e: Event) => this.patch({ description: value(e) })} /></label>
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
        <h2>${t("reminders.due")}</h2>
        ${this._open.length
          ? html`<pb-reminders .settings=${this.settings} .items=${this._open}></pb-reminders>`
          : html`<p class="muted">${t("reminders.none_due")}</p>`}
      </div>
      <div class="card">
        <h2>${t("reminders.title")}</h2>
        <p class="muted">${t("reminders.hint")}</p>
        ${this._items.length === 0
          ? html`<p class="muted">${t("common.empty")}</p>`
          : html`<ul class="list">
              ${this._items.map(
                (r) => html`<li>
                  <div class="grow">
                    <div class="row">
                      <strong class="ellipsis">${r.name}</strong>
                      ${r.active ? nothing : html`<span class="badge">${t("recurring.paused")}</span>`}
                    </div>
                    <div class="muted">
                      ${t("recurring.summary", { interval: r.interval, unit: t(UNIT[r.frequency]), date: formatDate(r.anchor_date) })}
                      ${[r.category_name, r.budget_name].filter(Boolean).map((name) => ` · ${name}`)}
                    </div>
                    ${r.last_opened_date
                      ? html`<div class="muted">${t("reminders.last", { date: formatDate(r.last_opened_date) })}</div>`
                      : nothing}
                  </div>
                  ${r.amount_minor !== null
                    ? html`<span class="amount ${r.kind === "income" ? "positive" : ""}">${formatMoney(r.amount_minor, currency)}</span>`
                    : nothing}
                  <button class="icon" aria-label=${t("common.edit")} @click=${() => this.edit(r)}><pb-icon .path=${UI_EDIT}></pb-icon></button>
                  <button class="icon" aria-label=${t("common.delete")} @click=${() => this.deleteItem(r)}><pb-icon .path=${UI_DELETE}></pb-icon></button>
                </li>`,
              )}
            </ul>`}
        <div class="actions"><button class="primary" @click=${() => this.edit(null)}>${t("reminders.new")}</button></div>
      </div>
      <pb-dialog
        .heading=${this._draft?.id ? t("reminders.edit") : t("reminders.new")}
        .open=${this._draft !== null}
        @closed=${() => (this._draft = null)}
      >
        ${this._draft ? this.renderForm(this._draft) : nothing}
      </pb-dialog>
    `;
  }
}
define("pb-reminder-rules", PbReminderRules);
