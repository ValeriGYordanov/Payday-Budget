import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  type ChartConfiguration,
  DoughnutController,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import { LitElement, css, html } from "lit";
import { type CurrencyInfo, formatMoney } from "../../money";

// Register only what the four charts use (smaller bundle).
Chart.register(
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  DoughnutController,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
);

export interface Palette {
  text: string;
  muted: string;
  grid: string;
  positive: string;
  negative: string;
  primary: string;
  series: string[];
}

function readPalette(element: Element): Palette {
  const style = getComputedStyle(element);
  const v = (name: string) => style.getPropertyValue(name).trim();
  return {
    text: v("--pb-text"),
    muted: v("--pb-text-muted"),
    grid: v("--pb-border"),
    positive: v("--pb-positive"),
    negative: v("--pb-negative"),
    primary: v("--pb-primary"),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--pb-chart-${i}`)),
  };
}

/** Axis / tooltip money: chart values are integer minor units; ticks are rounded. */
export function moneyTick(currency: CurrencyInfo) {
  return (value: string | number) => formatMoney(Math.round(Number(value)), currency);
}

/** Chart.js canvas inside a Lit element; redrawn on data or colour-scheme change. */
export abstract class ChartElement extends LitElement {
  private chart?: Chart;
  private readonly scheme = window.matchMedia("(prefers-color-scheme: dark)");
  private readonly onScheme = () => this.draw();

  static override styles = css`
    :host {
      display: block;
      position: relative;
      height: var(--pb-chart-height, 260px);
    }
  `;

  /** Chart config for the current data, or null when there is nothing to draw. */
  protected abstract chartConfig(palette: Palette): ChartConfiguration | null;

  override connectedCallback() {
    super.connectedCallback();
    this.scheme.addEventListener("change", this.onScheme);
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    this.scheme.removeEventListener("change", this.onScheme);
    this.chart?.destroy();
    this.chart = undefined;
  }

  override updated() {
    this.draw();
  }

  private draw() {
    this.chart?.destroy();
    this.chart = undefined;
    const canvas = this.renderRoot.querySelector("canvas");
    if (!canvas) return;
    const config = this.chartConfig(readPalette(this));
    if (!config) return;
    Chart.defaults.color = readPalette(this).muted;
    this.chart = new Chart(canvas, config);
  }

  override render() {
    return html`<canvas></canvas>`;
  }
}
