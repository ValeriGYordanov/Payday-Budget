import { html, nothing } from "lit";
import { api } from "../api";
import { confirmAction } from "../components/pb-dialog";
import "../components/pb-dialog";
import "../components/pb-icon";
import { t } from "../i18n";
import { UI_ARCHIVE, UI_DELETE, UI_DOWN, UI_EDIT, UI_UNARCHIVE, UI_UP } from "../icons";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Budget, BudgetList } from "../types";
import { define } from "../define";

/** Budgets: % per budget, sum indicator and unallocated (B1), archive (B4), order. */
export class PageBudgets extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _list: { state: true },
    _showArchived: { state: true },
    _editing: { state: true },
  };
  declare _list: BudgetList | null;
  declare _showArchived: boolean;
  /** null = closed, "new" = create, Budget = edit. */
  declare _editing: Budget | "new" | null;

  constructor() {
    super();
    this._list = null;
    this._showArchived = false;
    this._editing = null;
  }

  static override styles = [shared];

  protected async load() {
    this._list = await api.get<BudgetList>("budgets");
  }

  private async save(e: Event) {
    e.preventDefault();
    const data = new FormData(e.target as HTMLFormElement);
    const body = { name: String(data.get("name") ?? ""), percent: String(data.get("percent") ?? "") };
    const editing = this._editing;
    const ok = await this.write(() =>
      editing === "new" || editing === null
        ? api.post("budgets", { ...body, sort_order: this.nextSortOrder() })
        : api.patch(`budgets/${editing.id}`, body),
    );
    if (ok) this._editing = null;
  }

  private nextSortOrder(): number {
    return Math.max(0, ...(this._list?.items ?? []).map((b) => b.sort_order + 1));
  }

  /** Swap sort order with the neighbour (normalising to 0..n first). */
  private async move(budget: Budget, delta: -1 | 1) {
    const items = [...(this._list?.items ?? [])];
    const index = items.findIndex((b) => b.id === budget.id);
    const target = index + delta;
    if (target < 0 || target >= items.length) return;
    [items[index], items[target]] = [items[target], items[index]];
    await this.write(() =>
      Promise.all(
        items.map((b, order) => (b.sort_order === order ? null : api.patch(`budgets/${b.id}`, { sort_order: order }))),
      ),
    );
  }

  private async toggleArchived(budget: Budget) {
    if (await this.write(() => api.patch(`budgets/${budget.id}`, { archived: !budget.archived }))) {
      this._editing = null;
    }
  }

  private async deleteItem(budget: Budget) {
    if (!(await confirmAction(t("common.confirm_delete", { name: budget.name }), t("common.delete")))) return;
    if (await this.write(() => api.delete(`budgets/${budget.id}`))) this._editing = null;
  }

  override render() {
    const list = this._list;
    if (!list) return html`<p class="muted">${t("common.loading")}</p>`;
    const visible = list.items.filter((b) => this._showArchived || !b.archived);
    const editing = this._editing === "new" ? null : this._editing;
    return html`
      <div class="card">
        <div class="row">
          <strong class="grow">${t("budgets.allocated", { percent: list.allocated_percent })}</strong>
          <span class="muted">${t("budgets.unallocated", { percent: list.unallocated_percent })}</span>
        </div>
      </div>
      <div class="card">
        <ul class="list">
          ${visible.map(
            (b) => html`<li>
              <div class="grow">
                <div class="row">
                  <strong class="ellipsis">${b.name}</strong>
                  ${b.archived ? html`<span class="badge">${t("common.archived")}</span>` : nothing}
                </div>
                <div class="muted">${b.percent}%</div>
              </div>
              <button class="icon" aria-label="Up" @click=${() => this.move(b, -1)}><pb-icon .path=${UI_UP}></pb-icon></button>
              <button class="icon" aria-label="Down" @click=${() => this.move(b, 1)}><pb-icon .path=${UI_DOWN}></pb-icon></button>
              <button class="icon" aria-label=${t("common.edit")} @click=${() => (this._editing = b)}><pb-icon .path=${UI_EDIT}></pb-icon></button>
            </li>`,
          )}
        </ul>
        <div class="actions">
          <label class="row muted grow">
            <input type="checkbox" .checked=${this._showArchived} @change=${(e: Event) => (this._showArchived = (e.target as HTMLInputElement).checked)} />
            ${t("budgets.show_archived")}
          </label>
          <button class="primary" @click=${() => (this._editing = "new")}>${t("budgets.new")}</button>
        </div>
      </div>
      <pb-dialog
        .heading=${editing ? t("budgets.edit") : t("budgets.new")}
        .open=${this._editing !== null}
        @closed=${() => (this._editing = null)}
      >
        ${this._editing !== null
          ? html`<form @submit=${this.save}>
              <label class="field">${t("common.name")}<input name="name" required maxlength="100" .value=${editing?.name ?? ""} /></label>
              <label class="field">
                ${t("budgets.percent")}
                <input name="percent" required inputmode="decimal" pattern="\\d{1,3}(\\.\\d{1,2})?" .value=${editing?.percent ?? ""} />
              </label>
              <div class="actions">
                ${editing
                  ? html`<button type="button" class="danger" aria-label=${t("common.delete")} @click=${() => this.deleteItem(editing)}>
                        <pb-icon .path=${UI_DELETE}></pb-icon>
                      </button>
                      <button type="button" @click=${() => this.toggleArchived(editing)}>
                        <span class="row">
                          <pb-icon .path=${editing.archived ? UI_UNARCHIVE : UI_ARCHIVE}></pb-icon>
                          ${editing.archived ? t("common.unarchive") : t("common.archive")}
                        </span>
                      </button>
                      <span class="spacer"></span>`
                  : nothing}
                <button type="button" @click=${() => (this._editing = null)}>${t("common.cancel")}</button>
                <button class="primary" type="submit">${t("common.save")}</button>
              </div>
            </form>`
          : nothing}
      </pb-dialog>
    `;
  }
}
define("page-budgets", PageBudgets);
