import { css, html, nothing } from "lit";
import { api, query } from "../api";
import "../components/pb-icon";
import { formatDate } from "../dates";
import { kindLabel, t } from "../i18n";
import { UI_FILTER, UI_RECURRING } from "../icons";
import { type CurrencyInfo, formatMoney } from "../money";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { BudgetList, Category, Page, Period, Tag, Transaction, User } from "../types";

const PAGE_SIZE = 50;

interface Filters {
  period: string;
  date_from: string;
  date_to: string;
  kind: string;
  category: string;
  budget: string;
  tag: string;
  user: string;
  q: string;
}

const NO_FILTERS: Filters = {
  period: "current",
  date_from: "",
  date_to: "",
  kind: "",
  category: "",
  budget: "",
  tag: "",
  user: "",
  q: "",
};

/** Filterable transaction list; tap a row to edit or delete it (§6.6). */
export class PageTransactions extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _items: { state: true },
    _total: { state: true },
    _filters: { state: true },
    _showFilters: { state: true },
    _lists: { state: true },
  };
  declare _items: Transaction[];
  declare _total: number;
  declare _filters: Filters;
  declare _showFilters: boolean;
  declare _lists: {
    periods: Period[];
    categories: Category[];
    budgets: BudgetList["items"];
    tags: Tag[];
    users: User[];
  };

  private searchTimer?: number;

  constructor() {
    super();
    this._items = [];
    this._total = 0;
    this._filters = { ...NO_FILTERS };
    this._showFilters = false;
    this._lists = { periods: [], categories: [], budgets: [], tags: [], users: [] };
  }

  static override styles = [
    shared,
    css`
      .filters {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 0 12px;
      }
      .tx {
        cursor: pointer;
      }
      .tx pb-icon {
        color: var(--pb-text-muted);
        width: 18px;
        height: 18px;
      }
      .meta {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        align-items: center;
      }
    `,
  ];

  protected async load() {
    const [page, periods, categories, budgets, tags, users] = await Promise.all([
      this.fetchPage(0, this._items.length || PAGE_SIZE),
      api.get<{ items: Period[] }>("periods"),
      api.get<{ items: Category[] }>("categories"),
      api.get<BudgetList>("budgets"),
      api.get<{ items: Tag[] }>("tags"),
      api.get<{ items: User[] }>("users"),
    ]);
    this._items = page.items;
    this._total = page.total;
    this._lists = {
      periods: periods.items,
      categories: categories.items,
      budgets: budgets.items,
      tags: tags.items,
      users: users.items,
    };
  }

  private fetchPage(offset: number, limit: number) {
    return api.get<Page<Transaction>>(
      `transactions${query({ ...this._filters, limit: Math.min(limit, 500), offset })}`,
    );
  }

  private async more() {
    try {
      const page = await this.fetchPage(this._items.length, PAGE_SIZE);
      this._items = [...this._items, ...page.items];
      this._total = page.total;
    } catch (err) {
      this.fail(err);
    }
  }

  private async applyFilters(filters: Filters) {
    this._filters = filters;
    try {
      const page = await this.fetchPage(0, PAGE_SIZE);
      this._items = page.items;
      this._total = page.total;
    } catch (err) {
      this.fail(err);
    }
  }

  private setFilter(key: keyof Filters, value: string) {
    void this.applyFilters({ ...this._filters, [key]: value });
  }

  private setSearch(value: string) {
    window.clearTimeout(this.searchTimer);
    this.searchTimer = window.setTimeout(() => this.setFilter("q", value), 300);
  }

  private edit(transaction: Transaction) {
    this.dispatchEvent(
      new CustomEvent("pb-edit-transaction", { detail: transaction, bubbles: true, composed: true }),
    );
  }

  private select(key: keyof Filters, label: string, options: [string, string][]) {
    return html`<label class="field">
      ${label}
      <select @change=${(e: Event) => this.setFilter(key, (e.target as HTMLSelectElement).value)}>
        ${options.map(
          ([value, text]) =>
            html`<option value=${value} ?selected=${this._filters[key] === value}>${text}</option>`,
        )}
      </select>
    </label>`;
  }

  private renderFilters() {
    const l = this._lists;
    const f = this._filters;
    const all: [string, string] = ["", t("common.all")];
    return html`<div class="card">
      <div class="filters">
        ${this.select("period", t("filter.period"), [
          ["current", t("filter.current")],
          ["", t("filter.any_period")],
          ...l.periods.map((p): [string, string] => [String(p.id), p.name]),
        ])}
        <label class="field">
          ${t("filter.from")}
          <input type="date" .value=${f.date_from} @change=${(e: Event) => this.setFilter("date_from", (e.target as HTMLInputElement).value)} />
        </label>
        <label class="field">
          ${t("filter.to")}
          <input type="date" .value=${f.date_to} @change=${(e: Event) => this.setFilter("date_to", (e.target as HTMLInputElement).value)} />
        </label>
        ${this.select("kind", t("filter.kind"), [all, ["expense", kindLabel("expense")], ["income", kindLabel("income")]])}
        ${this.select("category", t("filter.category"), [
          all,
          ...l.categories.map((c): [string, string] => [String(c.id), `${c.name} (${kindLabel(c.kind)})`]),
        ])}
        ${this.select("budget", t("filter.budget"), [
          all,
          ...l.budgets.map((b): [string, string] => [String(b.id), b.name]),
        ])}
        ${this.select("tag", t("filter.tag"), [all, ...l.tags.map((tag): [string, string] => [String(tag.id), tag.name])])}
        ${this.select("user", t("filter.user"), [
          all,
          ...l.users.map((u): [string, string] => [u.id, u.name ?? u.id]),
        ])}
        <label class="field">
          ${t("filter.search")}
          <input type="search" .value=${f.q} @input=${(e: InputEvent) => this.setSearch((e.target as HTMLInputElement).value)} />
        </label>
      </div>
      <div class="actions">
        <button @click=${() => this.applyFilters({ ...NO_FILTERS })}>${t("filter.clear")}</button>
      </div>
    </div>`;
  }

  override render() {
    const currency: CurrencyInfo = { code: this.settings.currency, minorUnit: this.settings.minor_unit };
    return html`
      <div class="row">
        <span class="muted grow">${t("filter.count", { shown: this._items.length, total: this._total })}</span>
        <button aria-expanded=${this._showFilters} @click=${() => (this._showFilters = !this._showFilters)}>
          <span class="row"><pb-icon .path=${UI_FILTER}></pb-icon>${t("filter.title")}</span>
        </button>
      </div>
      <br />
      ${this._showFilters ? this.renderFilters() : nothing}
      <div class="card">
        ${this._items.length === 0
          ? html`<p class="muted">${t("common.empty")}</p>`
          : html`<ul class="list">
              ${this._items.map(
                (tx) => html`<li class="tx" tabindex="0" @click=${() => this.edit(tx)} @keydown=${(e: KeyboardEvent) => e.key === "Enter" && this.edit(tx)}>
                  <div class="grow">
                    <div class="ellipsis"><strong>${tx.description ?? tx.category_name}</strong></div>
                    <div class="meta muted">
                      <span>${formatDate(tx.date)}</span>
                      <span>· ${tx.category_name}</span>
                      ${tx.budget_name ? html`<span>· ${tx.budget_name}</span>` : nothing}
                      ${tx.created_by_name ? html`<span>· ${t("tx.by", { name: tx.created_by_name })}</span>` : nothing}
                      ${tx.recurring_rule_id !== null || tx.occurrence_date
                        ? html`<pb-icon .path=${UI_RECURRING} title=${t("tx.recurring")}></pb-icon>`
                        : nothing}
                      ${tx.tags.map((tag) => html`<span class="badge">${tag}</span>`)}
                    </div>
                  </div>
                  <span class="amount ${tx.kind === "income" ? "positive" : ""}">
                    ${tx.kind === "income" ? "+" : "−"}${formatMoney(tx.amount_minor, currency)}
                  </span>
                </li>`,
              )}
            </ul>`}
        ${this._items.length < this._total
          ? html`<div class="actions"><button @click=${this.more}>${t("common.load_more")}</button></div>`
          : nothing}
      </div>
    `;
  }
}
customElements.define("page-transactions", PageTransactions);
