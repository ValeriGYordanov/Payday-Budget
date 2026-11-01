import { css, html, nothing } from "lit";
import { api } from "../api";
import { confirmAction } from "../components/pb-dialog";
import "../components/pb-dialog";
import "../components/pb-icon";
import { kindLabel, t } from "../i18n";
import { ICONS, UI_ARCHIVE, UI_DELETE, UI_EDIT, UI_UNARCHIVE } from "../icons";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Category, Kind } from "../types";

interface Draft {
  id: number | null;
  name: string;
  kind: Kind;
  icon: string;
}

/** Categories per kind (C1), archive (C2), curated icon picker. */
export class PageCategories extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _items: { state: true },
    _draft: { state: true },
  };
  declare _items: Category[];
  declare _draft: Draft | null;

  constructor() {
    super();
    this._items = [];
    this._draft = null;
  }

  static override styles = [
    shared,
    css`
      .icons {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(44px, 1fr));
        gap: 4px;
        margin-bottom: 12px;
      }
      .icons button[aria-pressed="true"] {
        background: var(--pb-primary);
        color: var(--pb-on-primary);
      }
    `,
  ];

  protected async load() {
    this._items = (await api.get<{ items: Category[] }>("categories")).items;
  }

  private async save(e: Event) {
    e.preventDefault();
    const d = this._draft;
    if (!d) return;
    const body = { name: d.name, kind: d.kind, icon: d.icon };
    const ok = await this.write(() =>
      d.id === null ? api.post("categories", body) : api.patch(`categories/${d.id}`, body),
    );
    if (ok) this._draft = null;
  }

  private async deleteItem(c: Category) {
    if (await confirmAction(t("common.confirm_delete", { name: c.name }), t("common.delete"))) {
      await this.write(() => api.delete(`categories/${c.id}`));
    }
  }

  private renderKind(kind: Kind) {
    return html`<div class="card">
      <h2>${kindLabel(kind)}</h2>
      <ul class="list">
        ${this._items
          .filter((c) => c.kind === kind)
          .map(
            (c) => html`<li>
              <pb-icon .icon=${c.icon}></pb-icon>
              <div class="grow row">
                <span class="ellipsis">${c.name}</span>
                ${c.archived ? html`<span class="badge">${t("common.archived")}</span>` : nothing}
              </div>
              <button class="icon" aria-label=${t("common.edit")} @click=${() => (this._draft = { ...c })}>
                <pb-icon .path=${UI_EDIT}></pb-icon>
              </button>
              <button
                class="icon"
                aria-label=${c.archived ? t("common.unarchive") : t("common.archive")}
                @click=${() => this.write(() => api.patch(`categories/${c.id}`, { archived: !c.archived }))}
              >
                <pb-icon .path=${c.archived ? UI_UNARCHIVE : UI_ARCHIVE}></pb-icon>
              </button>
              <button class="icon" aria-label=${t("common.delete")} @click=${() => this.deleteItem(c)}>
                <pb-icon .path=${UI_DELETE}></pb-icon>
              </button>
            </li>`,
          )}
      </ul>
      <div class="actions">
        <button class="primary" @click=${() => (this._draft = { id: null, name: "", kind, icon: "mdi:tag" })}>
          ${t("categories.new")}
        </button>
      </div>
    </div>`;
  }

  override render() {
    const d = this._draft;
    return html`
      ${this.renderKind("expense")} ${this.renderKind("income")}
      <pb-dialog
        .heading=${d?.id ? t("categories.edit") : t("categories.new")}
        .open=${d !== null}
        @closed=${() => (this._draft = null)}
      >
        ${d
          ? html`<form @submit=${this.save}>
              <label class="field">
                ${t("common.name")}
                <input required maxlength="100" .value=${d.name} @input=${(e: InputEvent) => (this._draft = { ...d, name: (e.target as HTMLInputElement).value })} />
              </label>
              <div class="field">
                <div class="segmented" role="group" aria-label=${t("tx.kind")}>
                  ${(["expense", "income"] as Kind[]).map(
                    (kind) => html`<button type="button" aria-pressed=${d.kind === kind} @click=${() => (this._draft = { ...d, kind })}>
                      ${kindLabel(kind)}
                    </button>`,
                  )}
                </div>
              </div>
              <p class="muted">${t("categories.icon")}</p>
              <div class="icons">
                ${Object.keys(ICONS).map(
                  (name) => html`<button type="button" class="icon" title=${name} aria-pressed=${d.icon === name} @click=${() => (this._draft = { ...d, icon: name })}>
                    <pb-icon .icon=${name}></pb-icon>
                  </button>`,
                )}
              </div>
              <div class="actions">
                <button type="button" @click=${() => (this._draft = null)}>${t("common.cancel")}</button>
                <button class="primary" type="submit">${t("common.save")}</button>
              </div>
            </form>`
          : nothing}
      </pb-dialog>
    `;
  }
}
customElements.define("page-categories", PageCategories);
