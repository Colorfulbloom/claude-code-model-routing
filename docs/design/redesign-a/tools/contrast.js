(() => {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const blend = (top, bot) => ({ r: top.r * top.a + bot.r * (1 - top.a), g: top.g * top.a + bot.g * (1 - top.a), b: top.b * top.a + bot.b * (1 - top.a), a: 1 });
  const bgOf = (el) => { const stack = []; let e = el; while (e && e.nodeType === 1) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } e = e.parentElement; }
    let base = { r: 255, g: 255, b: 255, a: 1 }; if (!stack.length || stack[stack.length - 1].a < 1) base = parse(getComputedStyle(document.body).backgroundColor) || base;
    for (let i = stack.length - 1; i >= 0; i--) base = blend(stack[i], base); return base; };
  const hex = (c) => "#" + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
  const out = {};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = walker.nextNode())) {
    if (!n.textContent.trim()) continue; const el = n.parentElement; const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect(); if (!r.width || cs.visibility === "hidden" || el.closest("[hidden]")) continue;
    if (el.closest("svg") && el.tagName !== "text") continue;
    const fg0 = parse(cs.color); if (!fg0) continue; const bg = bgOf(el); const fg = fg0.a < 1 ? blend(fg0, bg) : fg0;
    const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const cls = (el.className && typeof el.className === "string" ? el.className.split(/\s+/)[0] : el.tagName.toLowerCase());
    const key = hex(fg) + " on " + hex(bg);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700; const large = size >= 24 || (size >= 18.66 && bold);
    if (!out[key] || out[key].ratio > ratio) out[key] = { ratio: Math.round(ratio * 100) / 100, sample: (cls + " '" + n.textContent.trim().slice(0, 24) + "'"), size, large, count: (out[key]?.count || 0) + 1 };
    else out[key].count++;
  }
  return { pairs: Object.entries(out).map(([k, v]) => ({ pair: k, ...v })).sort((a, b) => a.ratio - b.ratio) };
})()
