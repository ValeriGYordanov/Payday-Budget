import { describe, expect, it } from "vitest";
import { formatMoney, parseAmount, toDecimalString } from "./money";

const EUR = { code: "EUR", minorUnit: 2 };
const JPY = { code: "JPY", minorUnit: 0 };
const KWD = { code: "KWD", minorUnit: 3 };

describe("parseAmount (T1: integer minor units, no floats)", () => {
  it.each([
    ["12", 2, 1200],
    ["12.5", 2, 1250],
    ["12,50", 2, 1250],
    [" 0.01 ", 2, 1],
    ["0.10", 2, 10],
    ["007", 2, 700],
    ["12.", 2, 1200],
    ["1500", 0, 1500],
    ["1.234", 3, 1234],
    ["0.1", 2, 10],
    ["0.07", 2, 7],
  ])("%s with exponent %i -> %i", (input, exp, expected) => {
    expect(parseAmount(input, exp)).toBe(expected);
  });

  it.each([["12.345", 2], ["1.5", 0], ["-1", 2], ["1e3", 2], ["", 2], ["1,000.50", 2], ["abc", 2], ["99999999999999999", 2]])(
    "rejects %s with exponent %i",
    (input, exp) => {
      expect(parseAmount(input, exp)).toBeNull();
    },
  );
});

describe("toDecimalString", () => {
  it.each([
    [1250, 2, "12.50"],
    [5, 2, "0.05"],
    [-5, 2, "-0.05"],
    [0, 2, "0.00"],
    [1500, 0, "1500"],
    [1, 3, "0.001"],
  ])("%i (%i) -> %s", (minor, exp, expected) => {
    expect(toDecimalString(minor, exp)).toBe(expected);
  });

  it("rejects non-integers", () => {
    expect(() => toDecimalString(1.5, 2)).toThrow(RangeError);
  });
});

describe("formatMoney", () => {
  it("formats exactly in the given locale", () => {
    expect(formatMoney(123456, EUR, "en-IE")).toBe("€1,234.56");
    expect(formatMoney(-5, EUR, "en-IE")).toBe("-€0.05");
    expect(formatMoney(1500, JPY, "en-US")).toBe("¥1,500");
    expect(formatMoney(1234, KWD, "en-US")).toBe("KWD\u00a01.234");
  });

  it("keeps precision beyond float range", () => {
    expect(formatMoney(9007199254740991, EUR, "en-IE")).toBe("€90,071,992,547,409.91");
  });

  it("uses the locale's separators", () => {
    expect(formatMoney(123456, EUR, "de-DE")).toBe("1.234,56\u00a0€");
  });
});
