// Strings, numbers, cost, percent, month-first dates and hour labels.
// Every word on screen comes from strings.json through t(). Nothing here holds copy.

import { h } from "./h.js";

let STRINGS = {};

export function setStrings(map) {
  STRINGS = map && typeof map === "object" ? map : {};
}

// t("key", { name: value }) fills {name} slots. A missing key shows as its own name, so a gap is
// easy to see on screen. tests/test_static_strings.py keeps every literal key in strings.json.
export function t(key, slots) {
  if (!Object.prototype.hasOwnProperty.call(STRINGS, key) || typeof STRINGS[key] !== "string") return key;
  const raw = STRINGS[key];
  if (!slots) return raw;
  return raw.replace(/\{(\w+)\}/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(slots, name) ? String(slots[name]) : whole);
}

// Command-line flags such as --effort stay on one line (review #26). The old generator wrapped them
// in the finished HTML. This returns nodes, so the text is never parsed as markup.
const FLAG_SPLIT = /(?<![\w-])(--[a-z][a-z-]+)/;

export function renderText(text) {
  const out = [];
  String(text).split(FLAG_SPLIT).forEach((piece, i) => {
    if (piece === "") return;
    out.push(i % 2 === 1 ? h("span", { class: "nw" }, piece) : piece);
  });
  return out;
}

// tn("key", slots) is t() as nodes, with flags wrapped.
export function tn(key, slots) {
  return renderText(t(key, slots));
}

// ---------------------------------------------------------------- ranges

export const RANGES = ["today", "7d", "30d"];
export const DEFAULT_RANGE = "30d"; // gen3.py builds five of its six usage screens at 30 days

export function rangeWord(range) {
  if (range === "today") return t("r_today");
  if (range === "7d") return t("r_7d");
  return t("r_30d");
}

// ---------------------------------------------------------------- numbers

export function fmtTokens(n) {
  if (n === null || n === undefined) return "0";
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e4) return Math.round(n / 1e3) + "K";
  return Math.trunc(n).toLocaleString("en-US");
}

// "$289.40", or "Not priced" when there is no cost, or the cost is zero because nothing was priced.
export function fmtCost(cost, unpriced) {
  if (cost === null || cost === undefined || (cost === 0 && unpriced)) return t("not_priced");
  return "$" + cost.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function pct(x) {
  if (x === null || x === undefined) return "0%";
  const whole = Math.round(100 * x);
  return whole === 0 && x > 0 ? "<1%" : whole + "%";
}

// A share from the server (usage.py _shares): its whole percent, or "<1%" when lt1 is set.
export function shareText(share, lt1) {
  return lt1 ? "<1%" : (share || 0) + "%";
}

// Largest-remainder rounding so the shares add to 100. A share under half a percent that is not zero
// reads "<1%".
export function shares(values) {
  const total = values.reduce((a, b) => a + b, 0) || 1;
  const raw = values.map((v) => (100 * v) / total);
  const base = raw.map((r) => Math.floor(r));
  const left = 100 - base.reduce((a, b) => a + b, 0);
  const order = raw.map((r, i) => i).filter((i) => raw[i] > 0).sort((a, b) => raw[b] - base[b] - (raw[a] - base[a]));
  for (const i of order.slice(0, Math.max(left, 0))) base[i] += 1;
  return raw.map((r, i) => (r > 0 && (r < 0.5 || base[i] === 0) ? "<1%" : base[i] + "%"));
}

// ---------------------------------------------------------------- dates, month first, local time

function partsOf(date, options) {
  const out = {};
  for (const p of new Intl.DateTimeFormat("en-US", options).formatToParts(date)) out[p.type] = p.value;
  return out;
}

// "5:32 PM"
export function fmtClock(date) {
  const p = partsOf(date, { hour: "numeric", minute: "2-digit", hourCycle: "h12" });
  return p.hour + ":" + p.minute + " " + p.dayPeriod;
}

// "October 30"
export function fmtDate(date) {
  const p = partsOf(date, { month: "long", day: "numeric" });
  return p.month + " " + p.day;
}

// A date-only string ("2026-10-30") is a calendar date, so it becomes that date at local midnight in every
// time zone. Anything else returns null.
function dateOnly(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

// "October 30, 5:32 PM", from an ISO timestamp.
export function fmtTime(iso) {
  const day = dateOnly(iso);
  if (day) return fmtDate(day); // a date has no clock time, and must not slip to the day before
  const date = new Date(iso);
  return fmtDate(date) + ", " + fmtClock(date);
}

// "Oct 30", from an ISO date or timestamp. A date-only string keeps its own date. A full timestamp reads
// as the local calendar day, so "2026-10-31T02:00:00Z" is "Oct 30" in America/New_York.
export function fmtDay(iso) {
  const date = dateOnly(iso) || new Date(iso);
  const p = partsOf(date, { month: "short", day: "numeric" });
  return p.month + " " + p.day;
}

// "3 PM", for the hour axis of a today view. hour is 0 to 23.
export function fmtHour(hour) {
  const date = new Date(2000, 0, 1, hour, 0, 0);
  const p = partsOf(date, { hour: "numeric", hourCycle: "h12" });
  return p.hour + " " + p.dayPeriod;
}
