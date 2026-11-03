// The four settings the Settings page edits (model, effort, effort cap, compact window) and the pure rules that
// depend on which one a change belongs to. No DOM, no state, no copy and no imports, so the flow, the card and the
// builders can all read it without closing an import cycle.
//
// The key of a setting is what the server calls it: the "setting" field of a targets answer and a preview, and
// the last part of a history row's key_path.

export const EFFORT = "effortLevel";
export const CAP = "maxEffortLevel";
export const MODEL = "model";
export const COMPACT = "autoCompactWindow";

// In the order of the cells that edit them.
export const SETTING_KEYS = [MODEL, EFFORT, CAP, COMPACT];

// The cap values, low to high. max sets no cap.
export const RANKS = ["low", "medium", "high", "xhigh", "max"];

// The whole numbers the compact window takes.
export const COMPACT_MIN = 100000;
export const COMPACT_MAX = 1000000;

const has = (value) => value !== null && value !== undefined;
const isKey = (value) => typeof value === "string" && SETTING_KEYS.includes(value);

// The setting a targets answer, a preview or a backup preview is for. A body that names none is Effort's, as the
// server reads it.
export function settingOf(body) {
  return body && typeof body === "object" && isKey(body.setting) ? body.setting : EFFORT;
}

// The setting a history row or a saved edit changed: the last part of its key path. A path that names none of the four
// reads as Effort.
export function settingOfEdit(edit) {
  if (!edit || typeof edit !== "object") return EFFORT;
  const path = Array.isArray(edit.key_path) ? edit.key_path : [];
  const last = path.length ? path[path.length - 1] : edit.setting;
  return isKey(last) ? last : EFFORT;
}

// What was typed in the compact window box, as { ok, value }. Commas and white space are dropped, then it must be a
// whole number of digits from COMPACT_MIN to COMPACT_MAX. Anything else (a letter, a decimal, an exponent, a sign, nothing)
// is { ok: false }.
export function parseWindow(raw) {
  const digits = String(has(raw) ? raw : "").replace(/[\s,]/g, "");
  if (!/^\d+$/.test(digits)) return { ok: false, value: null };
  const value = Number(digits);
  if (!Number.isSafeInteger(value) || value < COMPACT_MIN || value > COMPACT_MAX) return { ok: false, value: null };
  return { ok: true, value };
}

// The cap limits of a level, lowest value first.
export function capLimits(limits) {
  const caps = (Array.isArray(limits) ? limits : []).filter((l) => l && l.kind === "cap");
  const rank = (l) => {
    const i = RANKS.indexOf(l.value);
    return i < 0 ? RANKS.length : i;
  };
  return caps.slice().sort((a, b) => rank(a) - rank(b));
}

// The options of the model pop-up, from the level rows in the server's order (each id, then its aliases). An alias is
// a name the models map gives the same display name as an id before it. models is the settings payload's { id or alias:
// display name }, or null. running is the level that runs now, chosen the level the owner picked or null. The running
// option is off once a model is chosen, as the running level radio is, and a blocked option is always off.
export function modelOptions(levels, models, { running = null, chosen = null } = {}) {
  const known = (name) => Boolean(models) && Object.prototype.hasOwnProperty.call(models, name);
  const seen = new Set();
  const out = [];
  for (const row of Array.isArray(levels) ? levels : []) {
    const value = row.level;
    const name = known(value) ? models[value] : value;
    const alias = known(value) && seen.has(name);
    if (known(value) && !alias) seen.add(name);
    const now = row.result === "now" || (has(running) && value === running);
    const blocked = row.allow === "blocked";
    out.push({
      value, name, alias, now, blocked, unclear: row.allow === "unclear",
      selected: chosen !== null ? value === chosen : now,
      disabled: blocked || (now && chosen !== null),
    });
  }
  return out;
}
