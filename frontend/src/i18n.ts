/** UI i18n: `t("key", {var})`. English only in v1 (§9). */
import { en } from "./i18n/en";

export type StringKey = keyof typeof en;

export function t(key: StringKey, vars: Record<string, string | number> = {}): string {
  return en[key].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

export function kindLabel(kind: "income" | "expense"): string {
  return t(kind === "income" ? "kind.income" : "kind.expense");
}
