// The Live page's "Dispatches in this session" card, drawn from session.runs[] of /api/live. Direction A, the
// dispatch canvas: one card per run on a dotted canvas, columns by depth (the main session, the agents it dispatched,
// the agents those dispatched), siblings in start order, and a curved connector from each dispatcher's out port to
// the run's in port. Siblings dispatched together share one trunk with an "agents at once" chip. A run that was
// resumed keeps its first connector and gets a second one from whoever resumed it, through the gutter into a bottom
// port, with a "Round n" chip. A run with no recorded dispatcher hangs off the main session on a dashed connector.
// At 720px and under the canvas becomes an indented vertical list in dispatch-tree order, with no connectors.
//
// The card is built once and then updated in place, like the rest of the page. Node maps keyed by run_id hold the
// cards, the connectors, the chips and the screen reader items, so a card that stays keeps its element, and the
// "Show n finished" button keeps its focus and its state across answers. update() runs on a changed answer,
// repaint() on the page's one-second clock (it only moves Working and Idle), and the page's reset on a project or
// session switch is a new session id. Nothing here parses markup: nodes come from h() and s(), and geometry goes
// through style.setProperty, because the page's Content-Security-Policy allows no inline style.
//
// Motion happens only on a changed answer after the first one: .lv-fl-enter on a new card, .lv-fl-draw on a new
// connector, .lv-fl-renew on a card whose latest round is new. The classes come off at the next changed answer, and
// live.css plays each of them once, under prefers-reduced-motion: no-preference only.
//
// The canvas and the card layer are aria-hidden. A visually hidden ordered list, one item per run in dispatch
// order, carries the same facts for a screen reader. The collapse button stays outside the hidden layer.

import { h, s, clear } from "../h.js";
import { t, fmtClock, fmtTokens } from "../format.js";
import { card } from "../components.js";

const MAIN_ID = "@main";
const CW = 252; // a card's width
const CH = 84; // a card's height
const STUB_H = 72; // the collapse button's height
const GX = 104; // the gap between columns
const GY = 14; // the gap between rows
const PAD = 24;
const PORT_Y = 30; // where the ports sit, from a card's top
const TAIL = 40; // room under the last card for a round chip
const LOOP_ROOM = 55; // from a resumed card's bottom to the next card in its column: the loop, its chip and the gap
const MANY = 12; // more cards than this collapse finished leaves
const MIN_STUB = 3; // a parent collapses its finished leaves from this many
const MOTION = ["lv-fl-enter", "lv-fl-draw", "lv-fl-renew"];

const list = (v) => (Array.isArray(v) ? v : []);
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const dateOf = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};
const ms = (iso) => {
  const d = typeof iso === "string" ? dateOf(iso) : null;
  return d ? d.getTime() : null;
};
const px = (n) => n + "px";

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function edgePath(x1, y1, x2, y2) {
  const c = Math.max(30, (x2 - x1) / 2);
  return "M" + x1 + "," + y1 + " C" + (x1 + c) + "," + y1 + " " + (x2 - c) + "," + y2 + " " + x2 + "," + y2;
}

// A later round, one rule for every loop: out of the resumer's right port, right into the gutter in front of the
// card (gx), up or down the gutter to 26 px under the card, right along under it and up into its bottom port. The
// gutter holds no cards, so the line never runs behind one.
function loopPath(x1, y1, gx, bx, by) {
  const low = by + 26;
  const dir = low >= y1 ? 1 : -1;
  const r = Math.min(12, Math.abs(low - y1) / 2);
  return "M" + x1 + "," + y1 + " H" + (gx - r) + " Q" + gx + "," + y1 + " " + gx + "," + (y1 + dir * r)
    + " V" + (low - dir * r) + " Q" + gx + "," + low + " " + (gx + r) + "," + low
    + " H" + (bx - 12) + " Q" + bx + "," + low + " " + bx + "," + (low - 12) + " V" + by;
}

// A branch of a trunk that has no recorded dispatcher: down the junction's own vertical, then right into the port.
// It keeps clear of the loop lines, which use the gutter just in front of the card.
function elbowPath(jx, jy, x2, y2) {
  const dy = y2 - jy;
  if (Math.abs(dy) < 1) return "M" + jx + "," + jy + " H" + x2;
  const dir = dy > 0 ? 1 : -1;
  const r = Math.min(12, Math.abs(dy));
  return "M" + jx + "," + jy + " V" + (y2 - dir * r) + " Q" + jx + "," + y2 + " " + (jx + r) + "," + y2 + " H" + x2;
}

// The layout. Runs come in dispatch order. A run whose dispatcher is not a run, or whose chain never reaches the main
// session, hangs off the main session. With more than MANY cards, each parent's finished single-round leaves collapse
// into one stub when there are MIN_STUB or more of them, and a parent in `expanded` shows them as well as the stub.
function arrange(runs, expanded) {
  const sorted = runs.map((run, i) => ({ run, i }))
    .sort((a, b) => (num(a.run.dispatch_order) - num(b.run.dispatch_order)) || a.i - b.i).map((x) => x.run);
  const byId = new Map(sorted.map((r) => [r.run_id, r]));
  const parentOf = new Map();
  for (const r of sorted) {
    if (r.run_id === MAIN_ID) continue;
    parentOf.set(r.run_id, typeof r.parent === "string" && r.parent !== r.run_id && byId.has(r.parent) ? r.parent : MAIN_ID);
  }
  for (const r of sorted) {
    let id = r.run_id;
    for (let steps = 0; id !== MAIN_ID && steps <= sorted.length; steps += 1) id = parentOf.get(id);
    if (id !== MAIN_ID) parentOf.set(r.run_id, MAIN_ID);
  }
  const kids = new Map();
  for (const r of sorted) {
    if (r.run_id === MAIN_ID) continue;
    const p = parentOf.get(r.run_id);
    if (!kids.has(p)) kids.set(p, []);
    kids.get(p).push(r);
  }
  const collapse = sorted.length > MANY;
  const finishedLeaf = (r) => r.state === "done" && list(r.rounds).length <= 1 && !(kids.get(r.run_id) || []).length;
  const items = [];
  const pos = new Map();
  let y = PAD; // the top of the next row
  const put = (id, run, stub, depth, parent) => {
    const it = { id, run, stub, depth, parent, x: PAD + depth * (CW + GX), y };
    items.push(it);
    pos.set(id, it);
    return it;
  };
  const place = (a, depth) => {
    let ks = kids.get(a.run_id) || [];
    let stub = null;
    if (collapse) {
      const done = ks.filter(finishedLeaf);
      if (done.length >= MIN_STUB) {
        const open = expanded.has(a.run_id);
        stub = { id: "stub:" + a.run_id, parent: a.run_id, runs: done, open };
        if (!open) ks = ks.filter((k) => !done.includes(k));
      }
    }
    const it = put(a.run_id, a, null, depth, a.run_id === MAIN_ID ? null : parentOf.get(a.run_id));
    const children = ks.map((run) => ({ run }));
    if (stub) children.unshift({ stub });
    if (!children.length) y += CH + GY;
    for (const child of children) {
      if (child.stub) {
        put(child.stub.id, null, child.stub, depth + 1, a.run_id);
        y += CH + GY;
      } else {
        place(child.run, depth + 1);
      }
    }
    // A resumed card's loop and chip run under it, so the next card in its column starts lower.
    if (list(a.rounds).length > 1) y = Math.max(y, it.y + CH + LOOP_ROOM);
  };
  place(byId.get(MAIN_ID), 0);
  const maxX = Math.max(...items.map((i) => i.x));
  const maxY = Math.max(...items.map((i) => i.y));
  const width = maxX + CW + PAD;
  const height = items.length === 1 ? PAD + CH + PAD : maxY + CH + PAD + TAIL;
  return { sorted, byId, parentOf, items, pos, width, height };
}

export function createFlow(deps) {
  const F = {
    sid: null, // the session the maps below belong to
    runs: [], // the last answer's runs, in dispatch order
    byId: new Map(),
    layout: null,
    narrow: false,
    nodes: new Map(), // run_id to a card
    stubs: new Map(), // "stub:" + the dispatcher's run_id to a collapse button
    edges: new Map(), // key to a connector
    chips: new Map(), // key to a chip
    sr: new Map(), // run_id to a screen reader item
    expanded: new Map(), // session id to the Set of dispatchers whose finished runs show
  };

  const media = typeof deps.narrow === "function" ? deps.narrow() : null;
  F.narrow = Boolean(media && media.matches);

  // ---------------------------------------------------------------- the card, built once

  const svg = s("svg", { class: "lv-fl-edges", "aria-hidden": "true", width: 0, height: 0 });
  const layer = h("div", { class: "lv-fl-cards", "aria-hidden": "true" });
  const stage = h("div", { class: "lv-fl-stage" }, svg, layer);
  const canvas = h("div", { class: "lv-fl-canvas" }, stage);
  const moreBelow = h("span", { class: "lv-fl-more", "aria-hidden": "true", hidden: true });
  const moreRight = h("span", { class: "lv-fl-more lv-fl-more-r", "aria-hidden": "true", hidden: true });
  const box = h("div", { class: "lv-fl-box" }, canvas);
  const hintRow = h("div", { class: "lv-fl-hints" }, moreBelow, moreRight);
  const slot = h("div", { class: "lv-fl-slot" });
  const empty = h("div", { class: "lv-fl-empty" },
    h("p", { class: "es-h" }, t("live_flow_empty_h")), h("p", { class: "es-t" }, t("live_flow_empty_t")));
  const note = h("p", { class: "lv-fl-note", hidden: true }, t("live_flow_legend_lines"));
  const unlinked = h("p", { class: "lv-fl-note lv-fl-unlinked", hidden: true });
  const srList = h("ol", { class: "lv-fl-sr" });
  const srw = h("div", { class: "lv-fl-srw" }, h("h3", null, t("live_flow_sr_list_h")), srList);
  const el = card({
    title: t("live_flow_h"), sub: t("live_flow_sub"), icon: "agents", cls: "lv-fl", body: [box, hintRow, slot, note, unlinked, srw],
  });
  el.hidden = true;

  // ---------------------------------------------------------------- words

  function labelOf(run) {
    const name = deps.agentName(run);
    return run.label_n ? name + " " + run.label_n : name;
  }

  const labelFor = (id) => (F.byId.has(id) ? labelOf(F.byId.get(id)) : t("row_main"));

  function stateWord(state) {
    if (state === "working") return t("live_working");
    if (state === "idle") return t("live_idle");
    return t("live_flow_done");
  }

  // Done comes from the server. Working and Idle come from the page's clock against active_at, so the card agrees
  // with the Agents card between answers.
  function stateNow(run) {
    if (run.state === "done") return "done";
    const now = deps.now();
    const last = ms(run.active_at);
    if (now === null || last === null) return run.state === "working" ? "working" : "idle";
    return now - last <= deps.activeMs ? "working" : "idle";
  }

  function durText(totalMs) {
    const seconds = Math.max(0, Math.floor(totalMs / 1000));
    if (seconds < 60) return t("live_flow_dur_s", { n: seconds });
    return t("live_flow_dur_min", { n: Math.floor(seconds / 60) });
  }

  function ranFor(run) {
    const rounds = list(run.rounds);
    if (!rounds.length) rounds.push({ started: run.started, last_request: run.last_request });
    let total = 0;
    for (const r of rounds) {
      const a = ms(r.started);
      const b = ms(r.last_request);
      if (a !== null && b !== null && b > a) total += b - a;
    }
    return total;
  }

  const lastRound = (run) => {
    const rounds = list(run.rounds);
    return rounds.length ? rounds[rounds.length - 1] : null;
  };
  const roundCount = (run) => Math.max(1, list(run.rounds).length);

  function roundTime(run) {
    const last = lastRound(run);
    const at = dateOf(last && last.started ? last.started : run.started);
    return at ? fmtClock(at) : "";
  }

  function metaText(run) {
    const n = roundCount(run);
    if (F.narrow && n > 1) {
      const last = lastRound(run);
      const resumer = last && typeof last.by === "string" ? F.byId.get(last.by) : null;
      if (resumer) return t("live_flow_resumed_by", { name: labelOf(resumer) }) + " · " + roundTime(run);
      return t("live_flow_round_chip", { n, time: roundTime(run) });
    }
    if (run.state === "done") return t("live_flow_ran_for", { dur: durText(ranFor(run)) });
    return t("live_flow_started_at", { time: roundTime(run) });
  }

  const figures = (tokens, cost) => fmtTokens(num(tokens)) + " · " + deps.costText(cost);

  function srText(run, state) {
    let text = labelOf(run) + ", " + deps.modelName(run) + " " + deps.effortText(run) + ", " + stateWord(state) + ".";
    if (run.run_id !== MAIN_ID) {
      if (run.parent_known === false) text += " " + t("live_flow_sr_no_dispatcher");
      else text += " " + t("live_flow_dispatched_by", { name: labelFor(run.parent) }) + ".";
    }
    const n = roundCount(run);
    if (n > 1) text += " " + t("live_flow_round_of", { n, total: n }) + ".";
    return text + " " + t("live_flow_tokens_cost", { tokens: fmtTokens(num(run.tokens)), cost: deps.costText(run.cost) });
  }

  // ---------------------------------------------------------------- cards

  function buildNode(run) {
    const n = h("span", { class: "lv-fl-n" });
    const bdg = h("span", { class: "lv-fl-bdg" });
    const name = h("span", { class: "lv-fl-name" });
    const st = h("span", { class: "lv-fl-st" });
    const meta = h("span", { class: "lv-fl-meta" });
    const tc = h("span", { class: "lv-fl-tc" });
    const r1 = h("div", { class: "lv-fl-r1" }, n, bdg);
    const out = h("span", { class: "lv-fl-port lv-fl-out" });
    const node = h("div", { class: "lv-fl-node", "data-run": run.run_id, "data-s": "idle" },
      r1, h("div", { class: "lv-fl-r2" }, name, st), h("div", { class: "lv-fl-r3" }, meta, tc),
      run.run_id === MAIN_ID ? null : h("span", { class: "lv-fl-port lv-fl-in" }), out);
    return { el: node, r1, n, bdg, name, st, meta, tc, out, rnd: null, bot: null, round: 0, state: "" };
  }

  function paintState(rec, state) {
    if (rec.state === state) return;
    rec.state = state;
    rec.el.setAttribute("data-s", state);
    rec.st.setAttribute("data-s", state);
    rec.st.textContent = stateWord(state);
  }

  function fillNode(rec, run) {
    setText(rec.n, run.run_id === MAIN_ID ? "" : String(num(run.dispatch_order)));
    setText(rec.bdg, deps.modelName(run) + " · " + deps.effortText(run));
    setText(rec.name, labelOf(run));
    paintState(rec, stateNow(run));
    setText(rec.meta, metaText(run));
    setText(rec.tc, figures(run.tokens, run.cost));
    const n = roundCount(run);
    if (n > 1) {
      if (!rec.rnd) {
        rec.rnd = h("span", { class: "lv-fl-rnd" });
        rec.r1.appendChild(rec.rnd);
        rec.bot = h("span", { class: "lv-fl-port lv-fl-bot" });
        rec.el.appendChild(rec.bot);
      }
      setText(rec.rnd, t("live_flow_round_badge", { n }));
    } else if (rec.rnd) {
      rec.r1.removeChild(rec.rnd);
      rec.el.removeChild(rec.bot);
      rec.rnd = null;
      rec.bot = null;
    }
  }

  // Wide: left and top from the layout. Narrow: the card's place in the list (order) and its indent.
  function placeNode(node, it, index) {
    const wide = !F.narrow;
    node.style.setProperty("left", wide ? px(it.x) : "");
    node.style.setProperty("top", wide ? px(it.y) : "");
    node.style.setProperty("order", wide ? "" : String(index));
    node.style.setProperty("margin-left", wide ? "" : px(Math.min(3, it.depth) * 14));
    node.setAttribute("data-depth", String(it.depth));
    node.setAttribute("data-link", it.run && it.run.parent_known === false ? "guess" : "known");
  }

  // ---------------------------------------------------------------- the collapse button

  function toggle(parentId) {
    let open = F.expanded.get(F.sid);
    if (!open) { open = new Set(); F.expanded.set(F.sid, open); }
    if (open.has(parentId)) open.delete(parentId);
    else open.add(parentId);
    render(false);
  }

  function buildStub(it) {
    const name = h("span", { class: "lv-fl-name" });
    const meta = h("span", { class: "lv-fl-meta" });
    const tc = h("span", { class: "lv-fl-tc" });
    const btn = h("button", {
      type: "button", class: "lv-fl-node lv-fl-stub", "data-run": it.id, "aria-expanded": "false", on: { click: () => toggle(it.stub.parent) },
    }, h("div", { class: "lv-fl-r2" }, name, h("span", { class: "lv-fl-st", "data-s": "done" }, t("live_flow_done"))),
    h("div", { class: "lv-fl-r3" }, meta, tc), h("span", { class: "lv-fl-port lv-fl-in" }));
    return { el: btn, name, meta, tc };
  }

  function fillStub(rec, stub) {
    const names = [];
    let tokens = 0;
    let cost = null;
    for (const r of stub.runs) {
      const name = deps.agentName(r);
      if (!names.includes(name)) names.push(name);
      tokens += num(r.tokens);
      if (typeof r.cost === "number") cost = (cost === null ? 0 : cost) + r.cost;
    }
    rec.el.setAttribute("aria-expanded", stub.open ? "true" : "false");
    setText(rec.name, stub.open ? t("live_flow_collapse_done") : t("live_flow_collapsed_done", { n: stub.runs.length }));
    setText(rec.meta, names.join(", "));
    setText(rec.tc, figures(tokens, cost));
  }

  // ---------------------------------------------------------------- connectors and chips (wide only)

  // The connectors the layout calls for, in drawing order. A key names one connector for as long as it exists, so
  // an old one keeps its element and only a new key can draw in.
  function connectors(L) {
    const edges = [];
    const chips = [];
    const groups = new Map();
    for (const r of L.sorted) {
      const key = r.together && typeof r.together.key === "string" ? r.together.key : null;
      if (key === null) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(r);
    }
    const drawn = new Set();
    for (const it of L.items) {
      if (it.parent === null) continue;
      const pp = L.pos.get(it.parent);
      const x1 = pp.x + CW;
      const y1 = pp.y + PORT_Y;
      const x2 = it.x;
      const y2 = it.y + PORT_Y;
      if (it.stub) {
        edges.push({ key: "s:" + it.id, d: edgePath(x1, y1, x2, y2) });
        continue;
      }
      const run = it.run;
      const n = roundCount(run);
      const live = run.state !== "done";
      // A resumed run's own line is quiet. The loop beside it carries the live color.
      const first = live && n === 1;
      const guess = run.parent_known === false;
      const key = run.together && typeof run.together.key === "string" ? run.together.key : null;
      const members = key === null ? [] : groups.get(key);
      if (members.length > 1 && members.every((m) => L.pos.has(m.run_id))) {
        // Dispatched together: one trunk from the dispatcher to a junction, then a branch to each card.
        const ys = members.map((m) => L.pos.get(m.run_id).y + PORT_Y);
        const jx = guess ? x2 - 72 : x2 - 40; // no dispatcher: its own vertical, away from the loop gutter
        const jy = (Math.min(...ys) + Math.max(...ys)) / 2;
        if (!drawn.has(key)) {
          drawn.add(key);
          edges.push({ key: "t:" + key, d: edgePath(x1, y1, jx, jy), live: members.some((m) => m.state !== "done" && roundCount(m) === 1), guess });
          chips.push({ key: "g:" + key, x: jx - 8, y: jy, kind: "g", text: t("live_flow_together", { n: members.length }) });
        }
        edges.push({ key: "b:" + run.run_id, d: guess ? elbowPath(jx, jy, x2, y2) : edgePath(jx, jy, x2, y2), live: first, guess });
      } else {
        // With no dispatcher the line turns at its own vertical, 72 px before the card, away from the loop gutter.
        const d = guess ? edgePath(x1, y1, x2 - 72, y2) + " H" + x2 : edgePath(x1, y1, x2, y2);
        edges.push({ key: "e:" + run.run_id, d, live: first, guess });
      }
      if (n > 1) {
        const last = lastRound(run);
        const by = last && typeof last.by === "string" && last.by !== run.run_id ? L.pos.get(last.by) : null;
        // The resumer's port when it is the card directly left of this one, else the dispatcher's.
        const src = by && !by.stub && by.depth === it.depth - 1 ? by : pp;
        const bx = x2 + 53;
        const bottom = it.y + CH + 5;
        edges.push({
          key: "l:" + run.run_id + ":" + n, loop: true, live, guess: false,
          d: loopPath(src.x + CW, src.y + PORT_Y, x2 - 30, bx, bottom),
        });
        chips.push({ key: "r:" + run.run_id + ":" + n, x: bx + 14, y: bottom + 26, kind: "r", text: t("live_flow_round_chip", { n, time: roundTime(run) }) });
      }
    }
    return { edges, chips };
  }

  function syncEdges(specs, animate) {
    const keep = new Set();
    for (const spec of specs) {
      keep.add(spec.key);
      let rec = F.edges.get(spec.key);
      if (!rec) {
        rec = { el: s("path", { d: spec.d, "data-edge": spec.key }), drawn: Boolean(animate) };
        F.edges.set(spec.key, rec);
        svg.appendChild(rec.el);
      }
      paintEdge(rec, spec);
    }
    for (const [key, rec] of F.edges) {
      if (!keep.has(key)) { svg.removeChild(rec.el); F.edges.delete(key); }
    }
  }

  function paintEdge(rec, spec) {
    rec.el.setAttribute("d", spec.d);
    rec.el.setAttribute("class", ["lv-fl-e", spec.live && "lv-fl-e-live", spec.loop && "lv-fl-e-loop", spec.guess && "lv-fl-e-guess", rec.drawn && "lv-fl-draw"]
      .filter(Boolean).join(" "));
    // A dashed connector cannot use the one-unit path length the draw-in needs.
    if (spec.guess) rec.el.removeAttribute("pathLength");
    else rec.el.setAttribute("pathLength", "1");
    rec.spec = spec;
  }

  function syncChips(specs) {
    const keep = new Set();
    for (const spec of specs) {
      keep.add(spec.key);
      let rec = F.chips.get(spec.key);
      if (!rec) {
        rec = { el: h("span", { class: "lv-fl-chip lv-fl-chip-" + spec.kind, "data-chip": spec.key }) };
        F.chips.set(spec.key, rec);
        layer.appendChild(rec.el);
      }
      setText(rec.el, spec.text);
      rec.el.style.setProperty("left", px(spec.x));
      rec.el.style.setProperty("top", px(spec.y - 10));
    }
    for (const [key, rec] of F.chips) {
      if (!keep.has(key)) { layer.removeChild(rec.el); F.chips.delete(key); }
    }
  }

  // ---------------------------------------------------------------- the visually hidden list

  function syncSr() {
    const desired = [];
    for (const run of F.runs) {
      let rec = F.sr.get(run.run_id);
      if (!rec) {
        rec = { el: h("li", { "data-run": run.run_id }), state: "" };
        F.sr.set(run.run_id, rec);
      }
      desired.push(rec);
      const state = stateNow(run);
      setText(rec.el, srText(run, state));
      rec.state = state;
    }
    const same = srList.childNodes.length === desired.length && desired.every((rec, i) => srList.childNodes[i] === rec.el);
    if (!same) {
      clear(srList);
      for (const rec of desired) srList.appendChild(rec.el);
    }
    const ids = new Set(F.runs.map((r) => r.run_id));
    for (const id of [...F.sr.keys()]) if (!ids.has(id)) F.sr.delete(id);
  }

  // ---------------------------------------------------------------- the scroll hints

  function setHint(node, n, one, many) {
    node.hidden = n === 0;
    if (n > 0) setText(node, n === 1 ? one : many);
  }

  function hints() {
    const high = num(canvas.clientHeight);
    const wide = num(canvas.clientWidth);
    const top = num(canvas.scrollTop);
    const left = num(canvas.scrollLeft);
    let below = 0;
    let right = 0;
    if (!F.narrow && high > 0 && wide > 0 && F.layout) {
      for (const it of F.layout.items) {
        if (it.y + 40 > top + high) below += 1;
        if (it.x + 40 > left + wide) right += 1;
      }
    }
    setHint(moreBelow, below, t("live_flow_more_below_1"), t("live_flow_more_below", { n: below }));
    setHint(moreRight, right, t("live_flow_more_right_1"), t("live_flow_more_right", { n: right }));
  }

  canvas.addEventListener("scroll", hints);

  // ---------------------------------------------------------------- one render

  function syncCards(L, animate) {
    const seenNodes = new Set();
    const seenStubs = new Set();
    L.items.forEach((it, index) => {
      if (it.stub) {
        seenStubs.add(it.id);
        let rec = F.stubs.get(it.id);
        if (!rec) {
          rec = buildStub(it);
          F.stubs.set(it.id, rec);
          stage.appendChild(rec.el);
        }
        fillStub(rec, it.stub);
        placeNode(rec.el, it, index);
        return;
      }
      seenNodes.add(it.id);
      let rec = F.nodes.get(it.id);
      const isNew = !rec;
      if (isNew) {
        rec = buildNode(it.run);
        F.nodes.set(it.id, rec);
        layer.appendChild(rec.el);
        if (animate) rec.el.classList.add("lv-fl-enter");
      }
      fillNode(rec, it.run);
      const n = roundCount(it.run);
      if (animate && n > 1 && (isNew || n > rec.round)) rec.el.classList.add("lv-fl-renew");
      rec.round = n;
      placeNode(rec.el, it, index);
    });
    for (const [id, rec] of F.nodes) {
      if (!seenNodes.has(id)) { layer.removeChild(rec.el); F.nodes.delete(id); }
    }
    for (const [id, rec] of F.stubs) {
      if (!seenStubs.has(id)) { stage.removeChild(rec.el); F.stubs.delete(id); }
    }
  }

  function render(animate) {
    const L = arrange(F.runs, F.expanded.get(F.sid) || new Set());
    F.layout = L;
    canvas.classList.toggle("lv-fl-narrow", F.narrow);
    syncCards(L, animate);
    const only = L.items.length === 1;
    const wide = !F.narrow;
    // With no agents the stage takes the canvas' width, so the empty note beside the main card has room.
    stage.style.setProperty("width", wide && !only ? px(L.width) : "");
    stage.style.setProperty("height", wide ? px(L.height) : "");
    svg.setAttribute("width", wide ? String(L.width) : "0");
    svg.setAttribute("height", wide ? String(L.height) : "0");
    if (wide) {
      const made = connectors(L);
      syncEdges(made.edges, animate);
      syncChips(made.chips);
    } else {
      syncEdges([], false);
      syncChips([]);
    }
    // No agents yet: beside the main card on the canvas, below it on a phone.
    if (only) {
      empty.classList.toggle("lv-fl-empty-in", wide);
      empty.style.setProperty("left", wide ? px(PAD + CW + 40) : "");
      empty.style.setProperty("top", wide ? px(PAD) : "");
      const home = wide ? stage : slot;
      if (empty.parentNode !== home) home.appendChild(empty);
    } else if (empty.parentNode) {
      empty.parentNode.removeChild(empty);
    }
    note.hidden = only || !wide;
    const lost = F.runs.filter((r) => r.run_id !== MAIN_ID && r.parent_known === false).length;
    unlinked.hidden = lost === 0;
    if (lost === 1) setText(unlinked, t("live_flow_no_dispatcher_1"));
    else if (lost > 1) setText(unlinked, t("live_flow_no_dispatcher", { n: lost }));
    syncSr();
    hints();
  }

  function stripMotion() {
    for (const rec of F.nodes.values()) {
      for (const name of MOTION) if (rec.el.classList.contains(name)) rec.el.classList.remove(name);
    }
    for (const rec of F.edges.values()) {
      if (!rec.drawn) continue;
      rec.drawn = false;
      paintEdge(rec, rec.spec);
    }
  }

  function dropMaps() {
    clear(layer);
    for (const rec of F.stubs.values()) stage.removeChild(rec.el);
    for (const rec of F.edges.values()) svg.removeChild(rec.el);
    F.nodes.clear();
    F.stubs.clear();
    F.edges.clear();
    F.chips.clear();
    F.sr.clear();
    F.layout = null;
  }

  if (media && typeof media.addEventListener === "function") {
    media.addEventListener("change", () => {
      F.narrow = Boolean(media.matches);
      if (F.runs.length) render(false);
    });
  }

  return {
    el,
    // A changed answer. animate is true only for a changed answer after the first one of this session.
    update(session, animate) {
      const runs = session && typeof session === "object" ? list(session.runs).filter((r) => r && typeof r === "object" && typeof r.run_id === "string") : [];
      if (!runs.some((r) => r.run_id === MAIN_ID)) {
        el.hidden = true;
        F.runs = [];
        F.byId = new Map();
        F.sid = null;
        dropMaps();
        return;
      }
      el.hidden = false;
      const sid = typeof session.session_id === "string" ? session.session_id : "";
      let motion = Boolean(animate);
      if (sid !== F.sid) {
        dropMaps();
        F.sid = sid;
        motion = false;
      }
      F.runs = runs;
      F.byId = new Map(runs.map((r) => [r.run_id, r]));
      stripMotion();
      render(motion);
    },
    // The one-second clock: Working and Idle move with it, nothing else does.
    repaint() {
      if (!F.runs.length) return;
      for (const run of F.runs) {
        const state = stateNow(run);
        const rec = F.nodes.get(run.run_id);
        if (rec) paintState(rec, state);
        const item = F.sr.get(run.run_id);
        if (item && item.state !== state) {
          item.state = state;
          setText(item.el, srText(run, state));
        }
      }
    },
  };
}
