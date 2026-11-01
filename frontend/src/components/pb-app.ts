import { LitElement, css, html, nothing } from "lit";
import { api, onChanged } from "../api";
import { type StringKey, t } from "../i18n";
import { UI_ADD, UI_CLOSE, UI_MENU } from "../icons";
import { errorMessage } from "../page";
import "../pages/page-budgets";
import "../pages/page-categories";
import "../pages/page-dashboard";
import "../pages/page-periods";
import "../pages/page-recurring";
import "../pages/page-settings";
import "../pages/page-setup";
import "../pages/page-tags";
import "../pages/page-transactions";
import { shared } from "../styles";
import type { Settings, Transaction } from "../types";
import "./pb-icon";
import type { PbTransactionDialog } from "./pb-transaction-dialog";
import "./pb-transaction-dialog";
import { define } from "../define";

const PAGES = [
  "dashboard",
  "transactions",
  "periods",
  "budgets",
  "categories",
  "tags",
  "recurring",
  "settings",
] as const;
type PageName = (typeof PAGES)[number];

function routeFromHash(): PageName {
  const name = location.hash.replace(/^#\/?/, "");
  return (PAGES as readonly string[]).includes(name) ? (name as PageName) : "dashboard";
}

/** App shell: navigation, setup gate, "Add transaction" on every page, live refresh. */
export class PbApp extends LitElement {
  static override properties = {
    _settings: { state: true },
    _page: { state: true },
    _revision: { state: true },
    _menuOpen: { state: true },
    _message: { state: true },
  };
  declare _settings: Settings | null;
  declare _page: PageName;
  declare _revision: number;
  declare _menuOpen: boolean;
  declare _message: string;

  private unsubscribe?: () => void;
  private refreshTimer?: number;
  private readonly onHash = () => {
    this._page = routeFromHash();
    this._menuOpen = false;
  };

  constructor() {
    super();
    this._settings = null;
    this._page = routeFromHash();
    this._revision = 0;
    this._menuOpen = false;
    this._message = "";
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
        min-height: 100dvh;
      }
      header {
        position: sticky;
        top: 0;
        z-index: 2;
        display: flex;
        align-items: center;
        gap: 4px;
        height: 56px;
        padding: 0 8px;
        background: var(--pb-header);
        color: var(--pb-on-header);
      }
      header h1 {
        font-size: 1.125rem;
        font-weight: 500;
        margin: 0;
      }
      header button.icon {
        color: inherit;
      }
      nav {
        position: fixed;
        inset: 56px auto 0 0;
        width: 240px;
        z-index: 3;
        background: var(--pb-surface);
        border-right: 1px solid var(--pb-border);
        padding: 8px 0;
        transform: translateX(-100%);
        transition: transform 0.15s ease;
        overflow-y: auto;
      }
      nav.open {
        transform: none;
      }
      nav a {
        display: block;
        padding: 12px 20px;
        color: var(--pb-text);
        text-decoration: none;
      }
      nav a[aria-current="page"] {
        color: var(--pb-primary);
        font-weight: 600;
        background: var(--pb-track);
      }
      .scrim {
        position: fixed;
        inset: 56px 0 0 0;
        z-index: 2;
        background: rgb(0 0 0 / 30%);
      }
      main {
        padding: 16px;
        padding-bottom: 96px;
        max-width: 960px;
        margin: 0 auto;
      }
      @media (min-width: 1024px) {
        nav {
          transform: none;
        }
        .scrim,
        .menu-button {
          display: none;
        }
        main {
          margin-left: 240px;
        }
      }
      .fab {
        position: fixed;
        right: 16px;
        bottom: 16px;
        z-index: 2;
        width: 56px;
        height: 56px;
        border-radius: 16px;
        border: none;
        background: var(--pb-primary);
        color: var(--pb-on-primary);
        box-shadow: 0 2px 8px rgb(0 0 0 / 30%);
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .message {
        position: fixed;
        left: 16px;
        right: 88px;
        bottom: 16px;
        z-index: 4;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 8px 8px 16px;
        border-radius: 8px;
        background: var(--pb-text);
        color: var(--pb-bg);
        max-width: 560px;
      }
      .message button.icon {
        color: inherit;
      }
    `,
  ];

  override connectedCallback() {
    super.connectedCallback();
    window.addEventListener("hashchange", this.onHash);
    void this.loadSettings();
    this.unsubscribe = onChanged(() => this.refresh());
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("hashchange", this.onHash);
    this.unsubscribe?.();
  }

  private async loadSettings() {
    try {
      this._settings = await api.get<Settings>("settings");
    } catch (err) {
      this._message = errorMessage(err);
    }
  }

  /** Data changed (SSE or own write): bump the revision so pages reload (debounced). */
  private refresh() {
    window.clearTimeout(this.refreshTimer);
    this.refreshTimer = window.setTimeout(() => {
      this._revision += 1;
      void this.loadSettings();
    }, 150);
  }

  private showMessage(text: string) {
    this._message = text;
  }

  private addTransaction(transaction: Transaction | null = null) {
    const dialog = this.renderRoot.querySelector<PbTransactionDialog>("pb-transaction-dialog");
    void dialog?.show(transaction);
  }

  private renderPage(settings: Settings) {
    const props = { settings, revision: this._revision };
    switch (this._page) {
      case "transactions":
        return html`<page-transactions
          .settings=${props.settings}
          .revision=${props.revision}
          @pb-edit-transaction=${(e: CustomEvent<Transaction>) => this.addTransaction(e.detail)}
        ></page-transactions>`;
      case "periods":
        return html`<page-periods .settings=${settings} .revision=${this._revision}></page-periods>`;
      case "budgets":
        return html`<page-budgets .settings=${settings} .revision=${this._revision}></page-budgets>`;
      case "categories":
        return html`<page-categories .settings=${settings} .revision=${this._revision}></page-categories>`;
      case "tags":
        return html`<page-tags .settings=${settings} .revision=${this._revision}></page-tags>`;
      case "recurring":
        return html`<page-recurring .settings=${settings} .revision=${this._revision}></page-recurring>`;
      case "settings":
        return html`<page-settings .settings=${settings} .revision=${this._revision}></page-settings>`;
      default:
        return html`<page-dashboard .settings=${settings} .revision=${this._revision}></page-dashboard>`;
    }
  }

  override render() {
    const settings = this._settings;
    const message = this._message
      ? html`<div class="message" role="alert">
          <span class="grow">${this._message}</span>
          <button class="icon" aria-label=${t("common.close")} @click=${() => (this._message = "")}>
            <pb-icon .path=${UI_CLOSE}></pb-icon>
          </button>
        </div>`
      : nothing;

    if (!settings) return html`<main><p class="muted">${t("common.loading")}</p></main>${message}`;
    if (!settings.setup_completed) {
      return html`<main @pb-error=${(e: CustomEvent<string>) => this.showMessage(e.detail)}>
          <page-setup @pb-changed=${() => this.refresh()}></page-setup>
        </main>
        ${message}`;
    }
    return html`
      <header>
        <button
          class="icon menu-button"
          aria-label="Menu"
          aria-expanded=${this._menuOpen}
          @click=${() => (this._menuOpen = !this._menuOpen)}
        >
          <pb-icon .path=${UI_MENU}></pb-icon>
        </button>
        <h1>${t(`nav.${this._page}` as StringKey)}</h1>
      </header>
      <nav class=${this._menuOpen ? "open" : ""}>
        ${PAGES.map(
          (name) =>
            html`<a href="#/${name}" aria-current=${name === this._page ? "page" : "false"}>
              ${t(`nav.${name}` as StringKey)}
            </a>`,
        )}
      </nav>
      ${this._menuOpen ? html`<div class="scrim" @click=${() => (this._menuOpen = false)}></div>` : nothing}
      <main
        @pb-error=${(e: CustomEvent<string>) => this.showMessage(e.detail)}
        @pb-changed=${() => this.refresh()}
      >
        ${this.renderPage(settings)}
      </main>
      <button class="fab" aria-label=${t("tx.add")} title=${t("tx.add")} @click=${() => this.addTransaction()}>
        <pb-icon .path=${UI_ADD}></pb-icon>
      </button>
      <pb-transaction-dialog
        .settings=${settings}
        @pb-changed=${() => this.refresh()}
      ></pb-transaction-dialog>
      ${message}
    `;
  }
}
define("pb-app", PbApp);
