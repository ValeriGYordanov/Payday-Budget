// @vitest-environment happy-dom
/**
 * §9 cards build smoke test: loads the built bundle (run `npm run build` first),
 * checks that all four cards register, and renders each from fake HA data.
 */
import { beforeAll, describe, expect, it } from "vitest";

// Resolved by Vite at test time; empty when the bundle has not been built.
const BUNDLE = import.meta.glob("../../../custom_components/payday_budget/www/payday-budget-cards.js");
const CARDS = [
  "payday-budget-progress-card",
  "payday-budget-periods-card",
  "payday-budget-category-card",
  "payday-budget-pace-card",
];

const period = {
  id: 2, name: "November 2026", start_date: "2026-11-01", end_date: null, is_current: true,
  days_elapsed: 3, created_by_id: null, created_by_name: null, created_at: "",
};
const summary = {
  period, currency: "EUR", minor_unit: 2, setup_completed: true,
  income_minor: 300000, expenses_minor: 4550, balance_minor: 295450,
  unallocated: { percent: "20.00", amount_minor: 60000 },
  budgets: [
    { budget_id: 1, name: "Needs", archived: false, percent: "50.00", target_minor: 150000, spent_minor: 4550, remaining_minor: 145450, percent_used: "3.03", over_target: false },
    { budget_id: 2, name: "Wants", archived: false, percent: "30.00", target_minor: 90000, spent_minor: 0, remaining_minor: 90000, percent_used: "0.00", over_target: false },
  ],
};
const responses: Record<string, unknown> = {
  "payday_budget/summary": summary,
  "payday_budget/history": { items: [{ period, income_minor: 300000, expenses_minor: 4550, budgets: [] }] },
  "payday_budget/breakdown": { period, budget_id: null, total_minor: 4550, categories: [{ category_id: 1, name: "Food", icon: "mdi:food", amount_minor: 4550 }] },
  "payday_budget/daily": { period, pace_length_days: 30, days: [{ date: "2026-11-01", spent_minor: 4550, cumulative_minor: 4550 }] },
};

function fakeHass(sent: Record<string, unknown>[]) {
  return {
    states: { "sensor.payday_budget_balance": { entity_id: "sensor.payday_budget_balance", state: "2954.50", last_updated: "1" } },
    entities: { "sensor.payday_budget_balance": { entity_id: "sensor.payday_budget_balance", platform: "payday_budget" } },
    connection: {
      sendMessagePromise: async (message: Record<string, unknown>) => {
        sent.push(message);
        return responses[message.type as string];
      },
    },
  };
}

type Card = HTMLElement & {
  setConfig(config: Record<string, unknown>): void;
  hass: unknown;
  getCardSize(): number;
  getGridOptions(): { rows: number };
  updateComplete: Promise<boolean>;
};

const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

describe("cards bundle", () => {
  beforeAll(async () => {
    const loaders = Object.values(BUNDLE);
    expect(loaders.length, "run `npm run build` before the tests").toBe(1);
    await loaders[0]();
  });

  it("registers the four cards for the card picker", () => {
    for (const name of CARDS) expect(customElements.get(name), name).toBeDefined();
    expect(window.customCards?.map((c) => c.type)).toEqual(CARDS);
  });

  it.each(CARDS)("%s renders from WebSocket data", async (name) => {
    const card = document.createElement(name) as Card;
    card.setConfig({ type: `custom:${name}` });
    const sent: Record<string, unknown>[] = [];
    card.hass = fakeHass(sent);
    document.body.append(card);
    await settle();
    await card.updateComplete;
    const text = card.shadowRoot?.textContent ?? "";
    expect(text).not.toContain("Payday Budget:"); // no error message
    expect(sent.length).toBeGreaterThan(0);
    expect(card.getCardSize()).toBeGreaterThan(0);
    expect(card.getGridOptions().rows).toBe(card.getCardSize());
    card.remove();
  });

  it("progress card filters by budget and passes options to the WebSocket API", async () => {
    const card = document.createElement("payday-budget-progress-card") as Card;
    card.setConfig({ type: "custom:payday-budget-progress-card", budget: "needs", period: "previous", title: "Needs" });
    const sent: Record<string, unknown>[] = [];
    card.hass = fakeHass(sent);
    document.body.append(card);
    await settle();
    expect(sent[0]).toEqual({ type: "payday_budget/summary", period: "previous" });
    const chart = card.shadowRoot?.querySelector("pb-progress-chart") as HTMLElement & { summary: typeof summary; showUnallocated: boolean };
    expect(chart.summary.budgets.map((b) => b.name)).toEqual(["Needs"]);
    expect(chart.showUnallocated).toBe(false);
    card.remove();
  });

  it("rejects invalid options", () => {
    const card = document.createElement("payday-budget-periods-card") as Card;
    expect(() => card.setConfig({ type: "x", limit: 0 })).toThrow(/limit/);
    expect(() => card.setConfig({ type: "x", budget: "Needs" })).toThrow(/Unknown option/);
    const pace = document.createElement("payday-budget-pace-card") as Card;
    expect(() => pace.setConfig({ type: "x", budget: "Needs" })).toThrow(/Unknown option/);
    expect(() => pace.setConfig({ type: "x", period: "last" })).toThrow(/period/);
  });

  it("refetches when a payday_budget entity changes", async () => {
    const card = document.createElement("payday-budget-pace-card") as Card;
    card.setConfig({ type: "custom:payday-budget-pace-card" });
    const sent: Record<string, unknown>[] = [];
    const hass = fakeHass(sent);
    card.hass = hass;
    document.body.append(card);
    await settle();
    const first = sent.length;
    card.hass = { ...hass }; // same states: no refetch
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(sent.length).toBe(first);
    card.hass = {
      ...hass,
      states: { "sensor.payday_budget_balance": { ...hass.states["sensor.payday_budget_balance"], last_updated: "2" } },
    };
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(sent.length).toBeGreaterThan(first);
    card.remove();
  });

  it("passes HA theme changes to the charts so they redraw", async () => {
    const card = document.createElement("payday-budget-pace-card") as Card;
    card.setConfig({ type: "custom:payday-budget-pace-card" });
    const hass = { ...fakeHass([]), themes: { theme: "default", darkMode: false } };
    card.hass = hass;
    document.body.append(card);
    await settle();
    await card.updateComplete;
    const chart = () => card.shadowRoot?.querySelector("pb-pace-chart") as HTMLElement & { theme: string };
    expect(chart().theme).toBe("default|false");
    card.hass = { ...hass, themes: { theme: "default", darkMode: true } };
    await card.updateComplete;
    expect(chart().theme).toBe("default|true");
    card.remove();
  });
});
