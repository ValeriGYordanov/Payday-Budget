/** Linear target pace in whole minor units: target x day / length, rounded half up (§8). */
export function paceTarget(targetMinor: number, day: number, lengthDays: number): number {
  if (day >= lengthDays) return targetMinor;
  return Math.floor((2 * targetMinor * day + lengthDays) / (2 * lengthDays));
}
