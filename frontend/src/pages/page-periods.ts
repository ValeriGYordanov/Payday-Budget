import { html, nothing } from "lit";
import { api } from "../api";
import { confirmAction } from "../components/pb-dialog";
import "../components/pb-dialog";
import "../components/pb-icon";
import { formatDate, todayIso } from "../dates";
import { t } from "../i18n";
import { UI_DELETE, UI_EDIT } from "../icons";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Period } from "../types";

/** Periods: list, start new (P3), edit start date / rename (P4, P5), delete (P5). */
export class PagePeriods extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _items: { state: true },
    _newDate: { state: true },
    _newName: { state: true },
    _editing: { state: true },
  };
  declare _items: Period[];
  declare _newDate: string;
  declare _newName: string;
  declare _editing: Period | null;

  constructor() {
    super();
    this._items = [];
    this._newDate = todayIso();
    this._newName = "";
    this._editing = null;
  }

  static override styles = [shared];

  protected async load() {
    this._items = (await api.get<{ items: Period[] }>("periods")).items;
  }

  private async start(e: Event) {
    e.preventDefault();
    const body = { start_date: this._newDate || null, name: this._newName.trim() || null };
    if (await this.write(() => api.post("periods", body))) {
      this._newName = "";
      this._newDate = todayIso();
    }
  }

  private async saveEdit(e: Event) {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const data = new FormData(form);
    const editing = this._editing;
    if (!editing) return;
    const ok = await this.write(() =>
      api.patch(`periods/${editing.id}`, {
        name: String(data.get("name") ?? ""),
        start_date: String(data.get("start_date") ?? ""),
      }),
    );
    if (ok) this._editing = null;
  }

  private async deleteItem(period: Period) {
    if (await confirmAction(t("periods.delete_confirm", { name: period.name }), t("common.delete"))) {
      await this.write(() => api.delete(`periods/${period.id}`));
    }
  }

  override render() {
    return html`
      <div class="card">
        <h2>${t("periods.start_new")}</h2>
        <form @submit=${this.start}>
          <label class="field">
            ${t("periods.start_date")}
            <input type="date" required max=${todayIso()} .value=${this._newDate} @input=${(e: InputEvent) => (this._newDate = (e.target as HTMLInputElement).value)} />
          </label>
          <label class="field">
            ${t("common.name")} (${t("common.optional")})
            <input maxlength="100" .value=${this._newName} @input=${(e: InputEvent) => (this._newName = (e.target as HTMLInputElement).value)} />
          </label>
          <div class="actions"><button class="primary" type="submit">${t("periods.start_new")}</button></div>
        </form>
      </div>
      <div class="card">
        <ul class="list">
          ${this._items.map(
            (p) => html`<li>
              <div class="grow">
                <div class="row">
                  <strong class="ellipsis">${p.name}</strong>
                  ${p.is_current ? html`<span class="badge">${t("periods.current")}</span>` : nothing}
                </div>
                <div class="muted">
                  ${formatDate(p.start_date)} – ${p.end_date ? formatDate(p.end_date) : t("periods.open")}
                </div>
              </div>
              <button class="icon" aria-label=${t("common.edit")} @click=${() => (this._editing = p)}>
                <pb-icon .path=${UI_EDIT}></pb-icon>
              </button>
              <button class="icon" aria-label=${t("common.delete")} @click=${() => this.deleteItem(p)}>
                <pb-icon .path=${UI_DELETE}></pb-icon>
              </button>
            </li>`,
          )}
        </ul>
      </div>
      <pb-dialog .heading=${t("periods.edit")} .open=${this._editing !== null} @closed=${() => (this._editing = null)}>
        ${this._editing
          ? html`<form @submit=${this.saveEdit}>
              <label class="field">
                ${t("common.name")}
                <input name="name" required maxlength="100" .value=${this._editing.name} />
              </label>
              <label class="field">
                ${t("periods.start_date")}
                <input name="start_date" type="date" required max=${todayIso()} .value=${this._editing.start_date} />
              </label>
              <div class="actions">
                <button type="button" @click=${() => (this._editing = null)}>${t("common.cancel")}</button>
                <button class="primary" type="submit">${t("common.save")}</button>
              </div>
            </form>`
          : nothing}
      </pb-dialog>
    `;
  }
}
customElements.define("page-periods", PagePeriods);
