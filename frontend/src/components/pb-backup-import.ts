import { LitElement, css, html, nothing } from "lit";
import { api } from "../api";
import { formatDate } from "../dates";
import { type StringKey, t } from "../i18n";
import { errorMessage } from "../page";
import { shared } from "../styles";
import { define } from "../define";

interface ImportResult {
  manifest: { app_version?: string; exported_at?: string };
  counts: Record<string, { file: number; current: number }>;
}

/** Tables shown in the preview; the others (links, snapshots, settings) follow them. */
const SHOWN = ["periods", "budgets", "categories", "tags", "transactions", "recurring_rules", "reminders"];

/**
 * Restore from a backup (v1.2 §5, D14): pick a file → the add-on validates it and reports
 * the counts (file vs. now) or the first error → Replace. Used in Settings and the wizard.
 */
export class PbBackupImport extends LitElement {
  static override properties = {
    _file: { state: true },
    _preview: { state: true },
    _error: { state: true },
    _busy: { state: true },
    _done: { state: true },
  };
  declare _file: File | null;
  declare _preview: ImportResult | null;
  declare _error: string;
  declare _busy: boolean;
  declare _done: boolean;

  constructor() {
    super();
    this._file = null;
    this._preview = null;
    this._error = "";
    this._busy = false;
    this._done = false;
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 8px 0;
      }
      th,
      td {
        text-align: left;
        padding: 4px 0;
      }
      td.n,
      th.n {
        text-align: right;
      }
    `,
  ];

  private async choose(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = "";
    this._file = file;
    this._preview = null;
    this._error = "";
    this._done = false;
    if (!file) return;
    this._busy = true;
    try {
      this._preview = await api.upload<ImportResult>("import?confirm=false", file);
    } catch (err) {
      this._error = errorMessage(err);
    } finally {
      this._busy = false;
    }
  }

  private async replace() {
    if (!this._file) return;
    this._busy = true;
    try {
      await api.upload<ImportResult>("import?confirm=true", this._file);
      this._preview = null;
      this._file = null;
      this._done = true;
      this.dispatchEvent(new CustomEvent("pb-changed", { bubbles: true, composed: true }));
    } catch (err) {
      this._error = errorMessage(err);
    } finally {
      this._busy = false;
    }
  }

  private renderPreview(p: ImportResult) {
    const exported = p.manifest.exported_at?.slice(0, 10);
    return html`
      ${exported
        ? html`<p class="muted">${t("backup.from", { date: formatDate(exported), version: p.manifest.app_version ?? "?" })}</p>`
        : nothing}
      <p>${t("backup.preview")}</p>
      <table>
        <tr><th>${t("backup.table")}</th><th class="n">${t("backup.now")}</th><th class="n">${t("backup.file")}</th></tr>
        ${SHOWN.filter((name) => p.counts[name]).map(
          (name) => html`<tr>
            <td>${t(`backup.${name}` as StringKey)}</td>
            <td class="n">${p.counts[name].current}</td>
            <td class="n">${p.counts[name].file}</td>
          </tr>`,
        )}
      </table>
      <div class="actions">
        <button @click=${() => (this._preview = null)}>${t("common.cancel")}</button>
        <button class="danger" ?disabled=${this._busy} @click=${this.replace}>${t("backup.replace")}</button>
      </div>
    `;
  }

  override render() {
    return html`
      <label class="field">
        ${t("backup.import")}
        <input type="file" accept=".zip,application/zip" ?disabled=${this._busy} @change=${this.choose} />
      </label>
      ${this._busy && !this._preview ? html`<p class="muted">${t("backup.checking")}</p>` : nothing}
      ${this._error ? html`<p class="error">${this._error}</p>` : nothing}
      ${this._done ? html`<p class="positive">${t("backup.done")}</p>` : nothing}
      ${this._preview ? this.renderPreview(this._preview) : nothing}
    `;
  }
}
define("pb-backup-import", PbBackupImport);
