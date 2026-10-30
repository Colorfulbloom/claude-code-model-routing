// Inline SVG icons in one stroke style, built with h.js. Ported from the round 1 to 3 generators.
// Cost has its own glyph ("coins"), distinct from the cache cylinder (review #21).

import { s } from "./h.js";

const rect = (x, y, width, height, rx) => ["rect", rx === undefined ? { x, y, width, height } : { x, y, width, height, rx }];
const circle = (cx, cy, r) => ["circle", { cx, cy, r }];
const path = (d) => ["path", { d }];

const ICONS = {
  overview: [rect(3, 3, 7, 7, 1.5), rect(14, 3, 7, 7, 1.5), rect(3, 14, 7, 7, 1.5), rect(14, 14, 7, 7, 1.5)],
  session: [rect(3, 4, 18, 16, 2), path("M7 9l3 3-3 3M12 15h5")],
  agents: [circle(9, 8, 3.5), path("M3 20a6 6 0 0 1 12 0M16 4.5a3.5 3.5 0 0 1 0 7M21 20a6 6 0 0 0-4.5-5.8")],
  issues: [path("M12 3l9.5 17h-19z"), path("M12 10v4M12 17.5v.5")],
  sources: [path("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z")],
  files: [path("M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"), path("M14 3v5h5M9 15l2 2 4-4")],
  rules: [path("M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"), path("M4 19a2 2 0 0 1 2-2h13M8 7h7")],
  chevron: [path("M6 9l6 6 6-6")],
  refresh: [path("M20 11a8 8 0 1 0-2.3 5.7"), path("M20 4v7h-7")],
  menu: [path("M4 7h16M4 12h16M4 17h16")],
  ring: [circle(12, 12, 8.5), path("M12 3.5V12l6 6")],
  shield: [path("M12 3l8 3v6c0 4.5-3.5 8-8 9-4.5-1-8-4.5-8-9V6z"), path("M9 12l2 2 4-4")],
  list: [path("M9 6h12M9 12h12M9 18h12"), path("M4 6h.5M4 12h.5M4 18h.5")],
  flag: [path("M5 21V4"), path("M5 4h12l-2.5 4L17 12H5")],
  clock: [circle(12, 12, 8.5), path("M12 7.5V12l3 2")],
  close: [path("M6 6l12 12M18 6L6 18")],
  version: [path("M12 3l8 4.5v9L12 21l-8-4.5v-9z"), path("M12 12l8-4.5M12 12v9M12 12L4 7.5")],
  cpu: [rect(5, 5, 14, 14, 2), rect(9, 9, 6, 6), path("M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3")],
  sliders: [path("M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"), circle(16, 6, 2), circle(10, 12, 2), circle(18, 18, 2)],
  coins: [circle(12, 12, 9), path("M12 6.5v11M14.6 9.3c-.3-1-1.3-1.6-2.6-1.6-1.5 0-2.6.8-2.6 1.9 0 2.6 5.3 1.3 5.3 4 0 1.1-1.1 1.9-2.7 1.9-1.4 0-2.4-.7-2.7-1.7")],
  bars: [path("M4 20V10M10 20V4M16 20v-7M22 20H2")],
  cache: [path("M4 7a8 3 0 0 1 16 0v10a8 3 0 0 1-16 0z"), path("M4 12a8 3 0 0 0 16 0")],
  calendar: [rect(3, 5, 18, 16, 2), path("M3 10h18M8 3v4M16 3v4")],
  arrow: [path("M5 12h14M13 6l6 6-6 6")],
  pin: [path("M12 17v5M8 3h8l-1 6 3 3H6l3-3z")],
  search: [circle(11, 11, 6.5), path("M20 20l-4.2-4.2")],
};

export const ICON_NAMES = Object.keys(ICONS);

export function icon(name, cls = "ic") {
  const parts = ICONS[name];
  if (!parts) throw new TypeError("unknown icon " + name);
  return s("svg", {
    class: cls, viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor",
    "stroke-width": 1.75, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  }, parts.map(([tag, attrs]) => s(tag, attrs)));
}
