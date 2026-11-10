import { LitElement, css, html, nothing } from "lit";
import { api } from "../api";
import { formatDate } from "../dates";
import { t } from "../i18n";
import { type CurrencyInfo, formatMoney } from "../money";
import { errorMessage } from "../page";
import { shared } from "../styles";
import type { ReminderOccurrence, Settings } from "../types";
import { define } from "../define";

/**
 * Open reminder occurrences (v1.2 §4.3) with Record and Ignore. With `max`, shows that
 * many and a "N more" link to the Recurring tab (the banner on every page).
 * Record dispatches `pb-record-reminder`; the app shell opens the pre-filled form.
 */
export class PbReminders extends LitElement {
  static override properties = {
    settings: { attribute: false },
    items: { attribute: false },
    max: { type: Number },
  };
  declare settings: Settings;
  declare items: ReminderOccurrence[];
  declare max: number;

  constructor() {
    super();
    this.items = [];
    this.max = 0;
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      li .actions {
        margin: 0;
        flex-wrap: nowrap;
      }
    `,
  ];

  private record(occurrence: ReminderOccurrence) {
    this.dispatchEvent(
      new CustomEvent("pb-record-reminder", { detail: occurrence, bubbles: true, composed: true }),
    );
  }

  private async ignore(occurrence: ReminderOccurrence) {
    try {
      await api.post(`reminders/occurrences/${occurrence.id}/dismiss`, {});
      this.dispatchEvent(new CustomEvent("pb-changed", { bubbles: true, composed: true }));
    } catch (err) {
      this.dispatchEvent(
        new CustomEvent("pb-error", { detail: errorMessage(err), bubbles: true, composed: true }),
      );
    }
  }

  override render() {
    const shown = this.max > 0 ? this.items.slice(0, this.max) : this.items;
    const more = this.items.length - shown.length;
    const currency: CurrencyInfo = { code: this.settings.currency, minorUnit: this.settings.minor_unit };
    return html`<ul class="list">
        ${shown.map(
          (o) => html`<li>
            <div class="grow">
              <strong class="ellipsis">${o.name}</strong>
              <div class="muted">
                ${t("reminders.due_on", { date: formatDate(o.due_date) })}${o.prefill.amount_minor !== null
                  ? ` · ${formatMoney(o.prefill.amount_minor, currency)}`
                  : ""}
              </div>
            </div>
            <div class="actions">
              <button @click=${() => this.ignore(o)}>${t("reminders.ignore")}</button>
              <button class="primary" @click=${() => this.record(o)}>${t("reminders.record")}</button>
            </div>
          </li>`,
        )}
      </ul>
      ${more > 0 ? html`<a href="#/recurring">${t("reminders.more", { count: more })}</a>` : nothing}`;
  }
}
define("pb-reminders", PbReminders);
