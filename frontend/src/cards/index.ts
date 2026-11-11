/** Cards bundle served by the integration (§7.1): payday-budget-cards.js. */
import { define, defineMissing } from "../define";
import { CategoryCard, ForecastCard, PaceCard, PeriodsCard, ProgressCard, UpcomingCard } from "./cards";

const CARDS = [
  ["payday-budget-progress-card", ProgressCard, "Payday Budget progress", "Target vs spent per budget, plus unallocated."],
  ["payday-budget-periods-card", PeriodsCard, "Payday Budget periods", "Income vs expenses for the last periods."],
  ["payday-budget-category-card", CategoryCard, "Payday Budget categories", "Spending by category for a period."],
  ["payday-budget-pace-card", PaceCard, "Payday Budget pace", "Cumulative spending vs a linear target."],
  ["payday-budget-forecast-card", ForecastCard, "Payday Budget forecast", "Projected balance, safe to spend per day and expected payday."],
  ["payday-budget-upcoming-card", UpcomingCard, "Payday Budget upcoming", "Recurring transactions and reminders expected before payday."],
] as const;

window.customCards = window.customCards ?? [];
for (const [type, card, name, description] of CARDS) {
  define(type, card);
  if (!window.customCards.some((c) => c.type === type)) {
    window.customCards.push({ type, name, description, preview: false });
  }
}

// HA defines <home-assistant> only after its registry polyfill is installed.
void customElements.whenDefined("home-assistant").then(defineMissing);

console.info(`%c PAYDAY-BUDGET-CARDS %c ${__APP_VERSION__} `, "color:white;background:#0288d1", "");
