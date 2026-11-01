import { describe, expect, it } from "vitest";
import { paceTarget } from "./pace";

describe("paceTarget (integer minor units)", () => {
  it("rises linearly and rounds half up", () => {
    expect(paceTarget(3000, 1, 30)).toBe(100);
    expect(paceTarget(1000, 1, 3)).toBe(333);
    expect(paceTarget(1000, 2, 3)).toBe(667);
    expect(paceTarget(5, 1, 2)).toBe(3); // 2.5 -> 3
  });

  it("stays flat after the line length", () => {
    expect(paceTarget(1000, 3, 3)).toBe(1000);
    expect(paceTarget(1000, 40, 30)).toBe(1000);
  });
});
