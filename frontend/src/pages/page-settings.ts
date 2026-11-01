import { html, nothing } from "lit";
import { api } from "../api";
import { confirmAction } from "../components/pb-dialog";
import "../components/pb-icon";
import { t } from "../i18n";
import { UI_COPY } from "../icons";
import { PageElement } from "../page";
import { shared } from "../styles";
import type { Currency } from "../types";


/** Settings: currency (K2: same exponent only, confirmed), integration token (§6.3). */
export class PageSettings extends PageElement {
  static override properties = {
    ...PageElement.properties,
    _currencies: { state: true },
    _token: { state: true },
    _copied: { state: true },
  };
  declare _currencies: Currency[];
  declare _token: string;
  declare _copied: boolean;

  constructor() {
    super();
    this._currencies = [];
    this._token = "";
    this._copied = false;
  }

  static override styles = [shared];

  protected async load() {
    this._currencies = (await api.get<{ items: Currency[] }>("currencies")).items;
    try {
      this._token = (await api.get<{ token: string }>("token")).token;
    } catch {
      this._token = ""; // only served through Ingress (§6.3), e.g. not in local dev
    }
  }

  private async changeCurrency(select: HTMLSelectElement) {
    const code = select.value;
    if (code === this.settings.currency) return;
    if (await confirmAction(t("settings.currency_confirm", { code }))) {
      await this.write(() => api.patch("settings", { currency: code, confirm: true }));
    }
    select.value = this.settings.currency;
  }

  private async copy() {
    try {
      await navigator.clipboard.writeText(this._token);
    } catch {
      // Clipboard API can be unavailable in iframes / non-secure contexts: select the text instead.
      const field = this.renderRoot.querySelector<HTMLInputElement>("#token");
      field?.select();
      document.execCommand("copy");
    }
    this._copied = true;
    window.setTimeout(() => (this._copied = false), 2000);
  }

  override render() {
    const sameExponent = this._currencies.filter((c) => c.minor_unit === this.settings.minor_unit);
    return html`
      <div class="card">
        <h2>${t("settings.currency")}</h2>
        <label class="field">
          <select aria-label=${t("settings.currency")} @change=${(e: Event) => this.changeCurrency(e.target as HTMLSelectElement)}>
            ${sameExponent.map(
              (c) => html`<option value=${c.code} ?selected=${c.code === this.settings.currency}>${c.code}</option>`,
            )}
          </select>
        </label>
        <p class="muted">${t("settings.currency_hint")}</p>
      </div>
      <div class="card">
        <h2>${t("settings.token")}</h2>
        <div class="row">
          <input id="token" readonly .value=${this._token} @focus=${(e: Event) => (e.target as HTMLInputElement).select()} />
          <button @click=${this.copy}>
            <span class="row"><pb-icon .path=${UI_COPY}></pb-icon>${this._copied ? t("settings.copied") : t("settings.copy")}</span>
          </button>
        </div>
        <p class="muted">${t("settings.token_hint")}</p>
      </div>
      <p class="muted">${t("settings.version", { version: __APP_VERSION__ })}</p>
      ${nothing}
    `;
  }
}
customElements.define("page-settings", PageSettings);
