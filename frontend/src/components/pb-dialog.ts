import { LitElement, css, html } from "lit";
import { t } from "../i18n";
import { UI_CLOSE } from "../icons";
import { shared } from "../styles";
import "./pb-icon";

/** Modal dialog on the native <dialog> element. Fires `closed` when dismissed. */
export class PbDialog extends LitElement {
  static override properties = { heading: {}, open: { type: Boolean, reflect: true } };
  declare heading: string;
  declare open: boolean;

  constructor() {
    super();
    this.heading = "";
    this.open = false;
  }

  static override styles = [
    shared,
    css`
      dialog {
        border: none;
        border-radius: 16px;
        padding: 0;
        width: min(560px, calc(100vw - 16px));
        max-height: calc(100dvh - 32px);
        background: var(--pb-surface);
        color: var(--pb-text);
      }
      dialog::backdrop {
        background: rgb(0 0 0 / 50%);
      }
      header {
        display: flex;
        align-items: center;
        padding: 8px 8px 0 16px;
      }
      header h2 {
        flex: 1;
        margin: 0;
      }
      .body {
        padding: 12px 16px 16px;
      }
    `,
  ];

  override updated(changed: Map<string, unknown>) {
    if (!changed.has("open")) return;
    const dialog = this.renderRoot.querySelector("dialog");
    if (!dialog) return;
    if (this.open && !dialog.open) dialog.showModal();
    if (!this.open && dialog.open) dialog.close();
  }

  close() {
    this.open = false;
    this.dispatchEvent(new CustomEvent("closed"));
  }

  override render() {
    return html`
      <dialog
        @cancel=${(e: Event) => {
          e.preventDefault();
          this.close();
        }}
      >
        <header>
          <h2>${this.heading}</h2>
          <button class="icon" aria-label=${t("common.close")} @click=${() => this.close()}>
            <pb-icon .path=${UI_CLOSE}></pb-icon>
          </button>
        </header>
        <div class="body"><slot></slot></div>
      </dialog>
    `;
  }
}
customElements.define("pb-dialog", PbDialog);

/** Ask for confirmation in a modal dialog (window.confirm may be blocked in iframes). */
export function confirmAction(message: string, confirmLabel = t("common.confirm")): Promise<boolean> {
  return new Promise((resolve) => {
    const dialog = document.createElement("pb-dialog") as PbDialog;
    dialog.heading = t("common.confirm");
    const finish = (result: boolean) => {
      dialog.remove();
      resolve(result);
    };
    const text = document.createElement("p");
    text.textContent = message;
    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;justify-content:flex-end;gap:8px";
    const cancel = document.createElement("button");
    cancel.textContent = t("common.cancel");
    cancel.onclick = () => finish(false);
    const confirm = document.createElement("button");
    confirm.textContent = confirmLabel;
    confirm.className = "pb-confirm-danger";
    confirm.onclick = () => finish(true);
    actions.append(cancel, confirm);
    dialog.append(text, actions);
    dialog.addEventListener("closed", () => finish(false));
    document.body.append(dialog);
    dialog.open = true;
  });
}
