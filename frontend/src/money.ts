/**
 * Money is integer minor units everywhere (§4). No floats: amounts are parsed and
 * formatted as decimal strings, and Intl only receives exact decimal strings.
 */

export interface CurrencyInfo {
  code: string;
  minorUnit: number;
}

const AMOUNT_RE = /^(\d+)(?:[.,](\d*))?$/;

/** "12.50" / "12,5" / "12" -> minor units; null if invalid or too precise. */
export function parseAmount(input: string, minorUnit: number): number | null {
  const match = AMOUNT_RE.exec(input.trim());
  if (!match) return null;
  const [, whole, fraction = ""] = match;
  if (fraction.length > minorUnit) return null;
  const digits = (whole + fraction.padEnd(minorUnit, "0")).replace(/^0+(?=\d)/, "");
  const value = Number(digits);
  return Number.isSafeInteger(value) ? value : null;
}

/** Minor units -> exact decimal string, e.g. 1250 (2) -> "12.50", -5 (2) -> "-0.05". */
export function toDecimalString(minor: number, minorUnit: number): string {
  if (!Number.isSafeInteger(minor)) throw new RangeError(`not an integer amount: ${minor}`);
  const sign = minor < 0 ? "-" : "";
  const digits = String(Math.abs(minor)).padStart(minorUnit + 1, "0");
  if (minorUnit === 0) return sign + digits;
  return `${sign}${digits.slice(0, -minorUnit)}.${digits.slice(-minorUnit)}`;
}

/** Form value for an amount: "12.50" (no grouping, "." separator). */
export function amountInputValue(minor: number, minorUnit: number): string {
  return toDecimalString(minor, minorUnit);
}

const formatters = new Map<string, Intl.NumberFormat>();

function formatter(currency: CurrencyInfo, locale?: string): Intl.NumberFormat {
  const key = `${locale ?? ""}|${currency.code}|${currency.minorUnit}`;
  let nf = formatters.get(key);
  if (!nf) {
    nf = new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency.code,
      minimumFractionDigits: currency.minorUnit,
      maximumFractionDigits: currency.minorUnit,
    });
    formatters.set(key, nf);
  }
  return nf;
}

/** Locale-formatted money, e.g. 123456 EUR -> "€1,234.56". */
export function formatMoney(minor: number, currency: CurrencyInfo, locale?: string): string {
  // Intl.NumberFormat formats numeric strings exactly (no float conversion).
  return formatter(currency, locale).format(
    toDecimalString(minor, currency.minorUnit) as Intl.StringNumericLiteral,
  );
}
