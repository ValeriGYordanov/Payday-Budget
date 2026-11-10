import { LitElement, css, html, nothing } from "lit";
import { t } from "../i18n";
import type { CurrencyInfo } from "../money";
import type { Summary } from "../types";
import type { CardConfig, HomeAssistant } from "./ha";

const DOMAIN = "payday_budget";
const REFRESH_DELAY_MS = 500;

type Option = "period" | "budget" | "limit" | "stacked" | "title";

/**
 * Base for the dashboard cards (§8): validates the YAML config, fetches through
 * the integration's WebSocket commands (§7.4) and refetches whenever a
 * payday_budget entity changes (they follow the add-on's SSE events).
 */
export abstract class PaydayCard extends LitElement {
  static override properties = {
    _config: { state: true },
    _error: { state: true },
    _loaded: { state: true },
    _theme: { state: true },
  };
  declare _config: CardConfig;
  declare _error: string;
  declare _loaded: boolean;
  /** Passed to the charts so they redraw with the new colours when HA's theme changes. */
  declare _theme: string;

  protected abstract readonly options: readonly Option[];
  protected abstract readonly rows: number;

  private _hass?: HomeAssistant;
  private entityIds: string[] = [];
  private entitiesSource?: HomeAssistant["entities"];
  private signature = "";
  private timer?: number;
  private loading = false;

  static override styles = css`
    :host {
      /* Chart colour tokens mapped onto the active HA theme. */
      --pb-text: var(--primary-text-color);
      --pb-text-muted: var(--secondary-text-color);
      --pb-border: var(--divider-color);
      --pb-surface: var(--card-background-color);
      --pb-track: var(--secondary-background-color);
      --pb-primary: var(--primary-color);
      --pb-positive: var(--success-color, #43a047);
      --pb-negative: var(--error-color, #db4437);
      --pb-warning: var(--warning-color, #ffa600);
      --pb-chart-1: var(--primary-color, #03a9f4);
      --pb-chart-2: #ff9800;
      --pb-chart-3: #9c27b0;
      --pb-chart-4: #4caf50;
      --pb-chart-5: #e91e63;
      --pb-chart-6: #009688;
      --pb-chart-7: #795548;
      --pb-chart-8: #607d8b;
      display: block;
    }
    .content {
      padding: 0 16px 16px;
    }
    .content.no-header {
      padding-top: 16px;
    }
    .message {
      color: var(--secondary-text-color);
      margin: 0;
    }
  `;

  setConfig(config: CardConfig): void {
    for (const key of Object.keys(config)) {
      if (key !== "type" && key !== "view_layout" && key !== "grid_options" && !this.options.includes(key as Option)) {
        throw new Error(`Unknown option "${key}" for ${config.type}`);
      }
    }
    if (config.period !== undefined && !/^(current|previous|\d+)$/.test(String(config.period))) {
      throw new Error('period must be "current", "previous" or a period id');
    }
    if (config.limit !== undefined && (!Number.isInteger(config.limit) || config.limit < 1 || config.limit > 120)) {
      throw new Error("limit must be a whole number from 1 to 120");
    }
    if (config.stacked !== undefined && typeof config.stacked !== "boolean") {
      throw new Error("stacked must be true or false");
    }
    if (config.budget !== undefined && !["string", "number"].includes(typeof config.budget)) {
      throw new Error("budget must be a budget name or id");
    }
    this._config = { ...config };
    this.signature = "";
    if (this._hass) this.schedule(0);
  }

  set hass(hass: HomeAssistant) {
    this._hass = hass;
    const theme = `${hass.themes?.theme ?? ""}|${hass.themes?.darkMode ?? ""}`;
    if (theme !== this._theme) this._theme = theme;
    if (hass.entities !== this.entitiesSource) {
      this.entitiesSource = hass.entities;
      this.entityIds = Object.values(hass.entities ?? {})
        .filter((e) => e.platform === DOMAIN)
        .map((e) => e.entity_id);
    }
    const signature = this.entityIds.map((id) => hass.states[id]?.last_updated ?? "").join("|");
    if (signature !== this.signature) {
      this.signature = signature;
      this.schedule(this._loaded ? REFRESH_DELAY_MS : 0);
    }
  }

  get hass(): HomeAssistant | undefined {
    return this._hass;
  }

  getCardSize(): number {
    return this.rows;
  }

  getGridOptions() {
    return { columns: 12, rows: this.rows, min_columns: 6, min_rows: 3 };
  }

  private schedule(delay: number) {
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => void this.refresh(), delay);
  }

  private async refresh() {
    if (!this._hass || !this._config || this.loading) return;
    this.loading = true;
    try {
      await this.fetchData();
      this._error = "";
    } catch (err) {
      this._error = (err as { message?: string })?.message ?? t("error.generic");
    } finally {
      this.loading = false;
      this._loaded = true;
    }
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    window.clearTimeout(this.timer);
  }

  override connectedCallback() {
    super.connectedCallback();
    if (this._hass && this._config) this.schedule(0);
  }

  protected ws<T>(command: string, params: Record<string, unknown> = {}): Promise<T> {
    if (!this._hass) return Promise.reject(new Error("not connected"));
    const message: Record<string, unknown> = { type: `${DOMAIN}/${command}` };
    for (const [key, value] of Object.entries(params)) if (value !== undefined) message[key] = value;
    return this._hass.connection.sendMessagePromise<T>(message);
  }

  protected period(): string | number {
    return this._config.period ?? "current";
  }

  protected currencyOf(summary: Summary): CurrencyInfo {
    return { code: summary.currency, minorUnit: summary.minor_unit };
  }

  protected abstract fetchData(): Promise<void>;
  protected abstract renderContent(): unknown;
  protected abstract defaultTitle(): string;

  override render() {
    if (!this._config) return nothing;
    const title = this._config.title ?? this.defaultTitle();
    const body = this._error
      ? html`<p class="message">Payday Budget: ${this._error}</p>`
      : this._loaded
        ? this.renderContent()
        : html`<p class="message">${t("common.loading")}</p>`;
    return html`<ha-card .header=${title || undefined}>
      <div class="content ${title ? "" : "no-header"}">${body}</div>
    </ha-card>`;
  }
}

/** Match a budget option (id or case-insensitive name) against summary rows. */
export function matchesBudget(option: string | number | undefined, id: number, name: string): boolean {
  if (option === undefined) return true;
  if (typeof option === "number") return option === id;
  return option.trim().toLowerCase() === name.toLowerCase() || option.trim() === String(id);
}
