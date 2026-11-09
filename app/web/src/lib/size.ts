/*
 * The size words for first run. The bar and the label both go by bytes. The unit comes from the
 * total, so "1.2 of 2.0 GB" never mixes units, and both numbers keep one decimal.
 */
const UNITS = [
  { name: "GB", size: 1_000_000_000 },
  { name: "MB", size: 1_000_000 },
  { name: "KB", size: 1_000 },
] as const;

function pick(total: number): { name: string; size: number } {
  return UNITS.find((unit) => total >= unit.size) ?? { name: "B", size: 1 };
}

/** "1.2 of 2.0 GB". Bytes show as whole numbers, every larger unit with one decimal. */
export function sizeParts(done: number, total: number): { done: string; total: string } {
  const unit = pick(total);
  const digits = unit.size === 1 ? 0 : 1;
  const show = (n: number) => (n / unit.size).toFixed(digits);
  return { done: show(Math.min(done, total)), total: `${show(total)} ${unit.name}` };
}

/** The bar's fill, 0 to 100, from bytes. */
export function percentOf(done: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((Math.min(done, total) / total) * 100);
}
