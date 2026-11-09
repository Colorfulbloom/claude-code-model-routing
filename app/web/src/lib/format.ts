/*
 * Cost and token words for Live. Costs are API list-price estimates. Below $1,000 they carry cents,
 * from $1,000 up they drop them (owner answer). A tiny non-zero cost reads "<$0.01", as the board
 * shows.
 */
import { t } from "@/strings/t";

const withCents = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const noCents = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/** "$8.28", "$1,235", "<$0.01" for a value under half a cent that is not zero, "$0.00" for zero. */
export function formatCost(dollars: number): string {
  if (dollars > 0 && dollars < 0.005) return "<$0.01";
  if (Math.round(dollars * 100) >= 100_000) return noCents.format(dollars);
  return withCents.format(dollars);
}

/** "at least $0.97", for a cost that leaves out requests with no price. */
export function formatCostAtLeast(dollars: number): string {
  return t("c_least", { cost: formatCost(dollars) });
}

/** "334K", "5.3M", "1.2B". Under 1,000 it is the plain number. Rounds to the unit shown. */
export function formatTokens(count: number): string {
  if (count >= 999_950_000) return `${trim(count / 1e9)}B`;
  if (count >= 999_500) return `${trim(count / 1e6)}M`;
  if (count >= 1e3) return `${String(Math.round(count / 1e3))}K`;
  return String(Math.round(count));
}

/** One decimal under 100 of the unit, none from 100 up (99.95 rounds to 100), so "5.3M" and "120M". */
function trim(value: number): string {
  return value >= 99.95 ? String(Math.round(value)) : value.toFixed(1);
}
