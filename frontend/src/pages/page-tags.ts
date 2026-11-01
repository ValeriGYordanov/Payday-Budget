import { html, nothing } from "lit";
import { api } from "../api";
import { confirmAction } from "../components/pb-dialog";
import "../components/pb-dialog";
import "../components/pb-icon";
import { t } from "../i18n";
import { UI_DELETE, UI_EDIT } from "../icons";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Tag } from "../types";
import { define } from "../define";

/** Tags: create, rename, delete (removes the tag from transactions). */
export class PageTags extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _items: { state: true },
    _newName: { state: true },
    _renaming: { state: true },
  };
  declare _items: Tag[];
  declare _newName: string;
  declare _renaming: Tag | null;

  constructor() {
    super();
    this._items = [];
    this._newName = "";
    this._renaming = null;
  }

  static override styles = [shared];

  protected async load() {
    this._items = (await api.get<{ items: Tag[] }>("tags")).items;
  }

  private async create(e: Event) {
    e.preventDefault();
    if (await this.write(() => api.post("tags", { name: this._newName }))) this._newName = "";
  }

  private async rename(e: Event) {
    e.preventDefault();
    const tag = this._renaming;
    if (!tag) return;
    const name = String(new FormData(e.target as HTMLFormElement).get("name") ?? "");
    if (await this.write(() => api.patch(`tags/${tag.id}`, { name }))) this._renaming = null;
  }

  private async deleteItem(tag: Tag) {
    if (await confirmAction(t("common.confirm_delete", { name: tag.name }), t("common.delete"))) {
      await this.write(() => api.delete(`tags/${tag.id}`));
    }
  }

  override render() {
    return html`
      <div class="card">
        <form class="row" @submit=${this.create}>
          <input required maxlength="100" placeholder=${t("tags.new")} aria-label=${t("tags.new")} .value=${this._newName} @input=${(e: InputEvent) => (this._newName = (e.target as HTMLInputElement).value)} />
          <button class="primary" type="submit">${t("common.add")}</button>
        </form>
      </div>
      <div class="card">
        ${this._items.length === 0
          ? html`<p class="muted">${t("common.empty")}</p>`
          : html`<ul class="list">
              ${this._items.map(
                (tag) => html`<li>
                  <span class="grow ellipsis">${tag.name}</span>
                  <button class="icon" aria-label=${t("common.edit")} @click=${() => (this._renaming = tag)}>
                    <pb-icon .path=${UI_EDIT}></pb-icon>
                  </button>
                  <button class="icon" aria-label=${t("common.delete")} @click=${() => this.deleteItem(tag)}>
                    <pb-icon .path=${UI_DELETE}></pb-icon>
                  </button>
                </li>`,
              )}
            </ul>`}
      </div>
      <pb-dialog .heading=${t("tags.rename")} .open=${this._renaming !== null} @closed=${() => (this._renaming = null)}>
        ${this._renaming
          ? html`<form @submit=${this.rename}>
              <label class="field">${t("common.name")}<input name="name" required maxlength="100" .value=${this._renaming.name} /></label>
              <div class="actions">
                <button type="button" @click=${() => (this._renaming = null)}>${t("common.cancel")}</button>
                <button class="primary" type="submit">${t("common.save")}</button>
              </div>
            </form>`
          : nothing}
      </pb-dialog>
    `;
  }
}
define("page-tags", PageTags);
