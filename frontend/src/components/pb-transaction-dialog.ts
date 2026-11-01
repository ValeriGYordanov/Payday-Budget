import { LitElement, css, html, nothing } from "lit";
import { ApiError, api } from "../api";
import { todayIso } from "../dates";
import { kindLabel, t } from "../i18n";
import { amountInputValue, parseAmount } from "../money";
import { errorMessage } from "../page";
import { shared } from "../styles";
import type { Budget, BudgetList, Category, Kind, Settings, Tag, Transaction } from "../types";
import { confirmAction } from "./pb-dialog";
import "./pb-dialog";
import { define } from "../define";

/** Fields that show their API error inline; other errors appear above the buttons. */
const INLINE_FIELDS = ["amount_minor", "category_id", "budget_id", "date"];

interface FormState {
  kind: Kind;
  amount: string;
  categoryId: string;
  budgetId: string;
  date: string;
  description: string;
  tags: string;
}

/**
 * Add / edit transaction (§6.6). Field order: kind, amount, category, budget,
 * date, description, tags. The budget is never prefilled for new transactions.
 */
export class PbTransactionDialog extends LitElement {
  static override properties = {
    settings: { attribute: false },
    _open: { state: true },
    _editing: { state: true },
    _form: { state: true },
    _categories: { state: true },
    _budgets: { state: true },
    _tags: { state: true },
    _error: { state: true },
    _errorField: { state: true },
    _busy: { state: true },
  };
  declare settings: Settings;
  declare _open: boolean;
  declare _editing: Transaction | null;
  declare _form: FormState;
  declare _categories: Category[];
  declare _budgets: Budget[];
  declare _tags: Tag[];
  declare _error: string;
  declare _errorField: string;
  declare _busy: boolean;

  constructor() {
    super();
    this._open = false;
    this._editing = null;
    this._form = this.emptyForm();
    this._categories = [];
    this._budgets = [];
    this._tags = [];
    this._error = "";
    this._errorField = "";
    this._busy = false;
  }

  static override styles = [
    shared,
    css`
      .two {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0 12px;
      }
      @media (max-width: 400px) {
        .two {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  private emptyForm(): FormState {
    return {
      kind: "expense",
      amount: "",
      categoryId: "",
      budgetId: "",
      date: todayIso(),
      description: "",
      tags: "",
    };
  }

  /** Open for a new transaction, or to edit `transaction`. */
  async show(transaction: Transaction | null = null) {
    this._editing = transaction;
    this._error = "";
    this._errorField = "";
    this._form = transaction
      ? {
          kind: transaction.kind,
          amount: amountInputValue(transaction.amount_minor, this.settings.minor_unit),
          categoryId: String(transaction.category_id),
          budgetId: transaction.budget_id === null ? "" : String(transaction.budget_id),
          date: transaction.date,
          description: transaction.description ?? "",
          tags: transaction.tags.join(", "),
        }
      : this.emptyForm();
    this._open = true;
    try {
      const [categories, budgets, tags] = await Promise.all([
        api.get<{ items: Category[] }>("categories"),
        api.get<BudgetList>("budgets"),
        api.get<{ items: Tag[] }>("tags"),
      ]);
      this._categories = categories.items;
      this._budgets = budgets.items;
      this._tags = tags.items;
    } catch (err) {
      this._error = errorMessage(err);
    }
  }

  private set<K extends keyof FormState>(key: K, value: FormState[K]) {
    this._form = { ...this._form, [key]: value };
  }

  private setKind(kind: Kind) {
    if (kind === this._form.kind) return;
    // Category kind must match (T2); incomes have no budget (B6).
    this._form = { ...this._form, kind, categoryId: "", budgetId: "" };
  }

  /** Active options, plus the archived one already on the transaction being edited. */
  private categoryOptions(): Category[] {
    return this._categories.filter(
      (c) =>
        c.kind === this._form.kind && (!c.archived || String(c.id) === this.originalCategoryId()),
    );
  }

  private budgetOptions(): Budget[] {
    return this._budgets.filter((b) => !b.archived || String(b.id) === this.originalBudgetId());
  }

  private originalCategoryId(): string {
    return this._editing ? String(this._editing.category_id) : "";
  }

  private originalBudgetId(): string {
    return this._editing?.budget_id != null ? String(this._editing.budget_id) : "";
  }

  private async save(e: Event) {
    e.preventDefault();
    const f = this._form;
    const amount = parseAmount(f.amount, this.settings.minor_unit);
    if (amount === null || amount <= 0) {
      this._error = t("tx.amount_invalid", { digits: this.settings.minor_unit });
      this._errorField = "amount_minor";
      return;
    }
    const body = {
      kind: f.kind,
      amount_minor: amount,
      category_id: f.categoryId ? Number(f.categoryId) : null,
      budget_id: f.kind === "expense" && f.budgetId ? Number(f.budgetId) : null,
      date: f.date || null,
      description: f.description.trim() || null,
      tags: f.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    this._busy = true;
    try {
      if (this._editing) await api.patch(`transactions/${this._editing.id}`, body);
      else await api.post("transactions", body);
      this.finish();
    } catch (err) {
      this._error = errorMessage(err);
      this._errorField = err instanceof ApiError ? (err.field ?? "") : "";
    } finally {
      this._busy = false;
    }
  }

  private async deleteItem() {
    if (!this._editing || !(await confirmAction(t("tx.delete_confirm"), t("common.delete")))) return;
    try {
      await api.delete(`transactions/${this._editing.id}`);
      this.finish();
    } catch (err) {
      this._error = errorMessage(err);
    }
  }

  private finish() {
    this._open = false;
    this.dispatchEvent(new CustomEvent("pb-changed", { bubbles: true, composed: true }));
  }

  private fieldError(field: string) {
    return this._errorField === field ? html`<span class="error">${this._error}</span>` : nothing;
  }

  override render() {
    const f = this._form;
    const decimals = this.settings?.minor_unit ?? 2;
    return html`
      <pb-dialog
        .heading=${this._editing ? t("tx.edit") : t("tx.add")}
        .open=${this._open}
        @closed=${() => (this._open = false)}
      >
        <form @submit=${this.save}>
          <div class="field">
            <div class="segmented" role="group" aria-label=${t("tx.kind")}>
              ${(["expense", "income"] as Kind[]).map(
                (kind) =>
                  html`<button
                    type="button"
                    aria-pressed=${f.kind === kind}
                    @click=${() => this.setKind(kind)}
                  >
                    ${kindLabel(kind)}
                  </button>`,
              )}
            </div>
          </div>
          <br />
          <label class="field">
            ${t("tx.amount")}
            <input
              required
              inputmode=${decimals > 0 ? "decimal" : "numeric"}
              autocomplete="off"
              .value=${f.amount}
              @input=${(e: InputEvent) => this.set("amount", (e.target as HTMLInputElement).value)}
            />
            ${this.fieldError("amount_minor")}
          </label>
          <div class="two">
            <label class="field">
              ${t("tx.category")}
              <select
                required
                .value=${f.categoryId}
                @change=${(e: Event) => this.set("categoryId", (e.target as HTMLSelectElement).value)}
              >
                <option value="" ?selected=${!f.categoryId}>${t("tx.choose")}</option>
                ${this.categoryOptions().map(
                  (c) =>
                    html`<option value=${c.id} ?selected=${String(c.id) === f.categoryId}>
                      ${c.name}
                    </option>`,
                )}
              </select>
              ${this.fieldError("category_id")}
            </label>
            ${f.kind === "expense"
              ? html`<label class="field">
                  ${t("tx.budget")}
                  <select
                    required
                    .value=${f.budgetId}
                    @change=${(e: Event) => this.set("budgetId", (e.target as HTMLSelectElement).value)}
                  >
                    <option value="" ?selected=${!f.budgetId}>${t("tx.choose")}</option>
                    ${this.budgetOptions().map(
                      (b) =>
                        html`<option value=${b.id} ?selected=${String(b.id) === f.budgetId}>
                          ${b.name}
                        </option>`,
                    )}
                  </select>
                  ${this.fieldError("budget_id")}
                </label>`
              : nothing}
          </div>
          <label class="field">
            ${t("tx.date")}
            <input
              type="date"
              required
              .value=${f.date}
              @input=${(e: InputEvent) => this.set("date", (e.target as HTMLInputElement).value)}
            />
            ${this.fieldError("date")}
          </label>
          <label class="field">
            ${t("tx.description")} (${t("common.optional")})
            <input
              maxlength="500"
              .value=${f.description}
              @input=${(e: InputEvent) => this.set("description", (e.target as HTMLInputElement).value)}
            />
          </label>
          <label class="field">
            ${t("tx.tags")} (${t("tx.tags_hint")})
            <input
              list="pb-tag-options"
              autocomplete="off"
              .value=${f.tags}
              @input=${(e: InputEvent) => this.set("tags", (e.target as HTMLInputElement).value)}
            />
            <datalist id="pb-tag-options">
              ${this._tags.map((tag) => html`<option value=${tag.name}></option>`)}
            </datalist>
          </label>
          ${this._error && !INLINE_FIELDS.includes(this._errorField)
            ? html`<p class="error">${this._error}</p>`
            : nothing}
          <div class="actions">
            ${this._editing
              ? html`<button type="button" class="danger" @click=${this.deleteItem}>
                    ${t("common.delete")}
                  </button>
                  <span class="spacer"></span>`
              : nothing}
            <button type="button" @click=${() => (this._open = false)}>${t("common.cancel")}</button>
            <button type="submit" class="primary" ?disabled=${this._busy}>${t("common.save")}</button>
          </div>
        </form>
      </pb-dialog>
    `;
  }
}
define("pb-transaction-dialog", PbTransactionDialog);
