(() => {
  const vw = document.documentElement.clientWidth;
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const label = (el) => (el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title") ||
    (el.labels && el.labels.length ? "lab" : "") || el.textContent.trim() || (el.querySelector("img[alt],svg[aria-label]") ? "img" : "")).slice(0, 40);
  const desc = (el) => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "");
  const overflow = [];
  for (const el of document.querySelectorAll("body *")) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && overflow.length < 12) {
      // skip if inside a horizontally scrolling ancestor
      let p = el.parentElement, scroller = false;
      while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(auto|scroll)/.test(cs.overflowX) || cs.overflowX === "hidden" || cs.overflowX === "clip") { scroller = true; break; } p = p.parentElement; }
      if (!scroller) overflow.push(desc(el) + " r=" + Math.round(r.right));
    }
  }
  const small = [], unnamed = [];
  for (const el of document.querySelectorAll("a[href],button,input,select,textarea,summary,[role=button],[role=tab],[tabindex]:not([tabindex='-1'])")) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    if ((r.width < 24 || r.height < 24) && small.length < 15) small.push(desc(el) + " " + Math.round(r.width) + "x" + Math.round(r.height) + " '" + el.textContent.trim().slice(0, 20) + "'");
    if (!label(el) && unnamed.length < 10) unnamed.push(desc(el));
  }
  const heads = [...document.querySelectorAll("h1,h2,h3")].filter(vis).slice(0, 25).map((e) => e.tagName + " " + e.textContent.trim().replace(/\s+/g, " ").slice(0, 50));
  const lm = [...document.querySelectorAll("main,nav,header,aside,footer,[role=main],[role=navigation],[role=banner],[role=status],[aria-live]")].map((e) => e.tagName.toLowerCase() + (e.getAttribute("role") ? "[" + e.getAttribute("role") + "]" : "") + (e.getAttribute("aria-live") ? "[live=" + e.getAttribute("aria-live") + "]" : ""));
  const svgs = [...document.querySelectorAll("svg")].filter(vis);
  const svgNoName = svgs.filter((s) => s.getAttribute("aria-hidden") !== "true" && !s.getAttribute("aria-label") && !s.getAttribute("aria-labelledby") && !s.querySelector("title") && !s.closest("[aria-hidden=true]")).length;
  return { title: document.title, docH: Math.ceil(document.documentElement.scrollHeight), scrollW: document.documentElement.scrollWidth, vw,
    overflow, small, unnamed, heads, landmarks: [...new Set(lm)], svgs: svgs.length, svgNoName,
    colorScheme: document.querySelector("meta[name=color-scheme]")?.content || null,
    bodyFont: getComputedStyle(document.body).fontFamily.slice(0, 40), bodySize: getComputedStyle(document.body).fontSize };
})()
