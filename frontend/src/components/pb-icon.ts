import { LitElement, css, html, svg } from "lit";
import { iconPath } from "../icons";

/** An MDI icon by name (`icon="mdi:food"`) or raw SVG path (`path=...`). */
export class PbIcon extends LitElement {
  static override properties = { icon: {}, path: {} };
  declare icon: string;
  declare path: string;

  constructor() {
    super();
    this.icon = "";
    this.path = "";
  }

  static override styles = css`
    :host {
      display: inline-flex;
      width: 24px;
      height: 24px;
      flex: none;
    }
    svg {
      width: 100%;
      height: 100%;
      fill: currentColor;
    }
  `;

  override render() {
    const d = this.path || iconPath(this.icon);
    return html`<svg viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${d}></path>`}</svg>`;
  }
}
customElements.define("pb-icon", PbIcon);
