// Capture the current dashboard over CDP. Usage: node --experimental-websocket capture.mjs shots.json outdir
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const [,, shotsFile, outDir] = process.argv;
const shots = JSON.parse(fs.readFileSync(shotsFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const prof = fs.mkdtempSync(path.join(outDir, "..", "prof-"));
const PORT = 9333 + Math.floor(Math.random() * 400);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`, "--no-first-run",
  "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"], { stdio: "ignore" });
const kill = () => { try { chrome.kill("SIGKILL"); } catch {} };
process.on("exit", kill);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let wsUrl;
for (let i = 0; i < 50 && !wsUrl; i++) {
  await sleep(200);
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    const p = list.find((t) => t.type === "page");
    if (p) wsUrl = p.webSocketDebuggerUrl;
  } catch {}
}
const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map();
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;

await send("Page.enable"); await send("Runtime.enable");
const SCAN = fs.readFileSync(new URL(process.env.SCAN || "./scan.js", import.meta.url), "utf8");
const report = [];
for (const s of shots) {
  const w = s.width, h = w < 600 ? 812 : 900;
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: w < 600 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: s.theme }, { name: "prefers-reduced-motion", value: "reduce" }] });
  await send("Page.navigate", { url: "about:blank" });
  await sleep(150);
  await send("Page.navigate", { url: s.url });
  await sleep(s.wait || 2500);
  if (s.js) { await evalJs(s.js); await sleep(s.after || 800); }
  for (let k = 0; k < (s.tabs || 0); k++) {
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await sleep(60);
  }
  if (s.tabs) { await sleep(400); s.focusInfo = await evalJs("(()=>{const e=document.activeElement;const cs=getComputedStyle(e);return e.tagName+' '+(e.className||'')+' \''+e.textContent.trim().slice(0,30)+'\' outline='+cs.outlineStyle+' '+cs.outlineWidth+' '+cs.outlineColor})()"); console.log('focus', s.focusInfo); }
  const info = await evalJs(SCAN);
  const fullH = Math.min(Math.max(info?.docH || h, h), 16000);
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: s.viewportOnly ? h : fullH, deviceScaleFactor: 1, mobile: w < 600 });
  await sleep(400);
  const shot = await send("Page.captureScreenshot", s.clip ? { format: "png", captureBeyondViewport: false, clip: { x: 0, y: s.clip[0], width: w, height: Math.min(s.clip[1], fullH - s.clip[0]), scale: 1 } } : { format: "png", captureBeyondViewport: false });
  const file = path.join(outDir, `${s.name}-${w}-${s.theme}.png`);
  fs.writeFileSync(file, Buffer.from(shot.result.data, "base64"));
  report.push({ focus: s.focusInfo, name: s.name, width: w, theme: s.theme, file, ...info });
  console.log(s.name, w, s.theme, info?.docH, info?.overflow?.length ?? "-");
}
fs.writeFileSync(path.join(outDir, "report.json"), JSON.stringify(report, null, 1));
ws.close(); kill();
await sleep(500); try { fs.rmSync(prof, { recursive: true, force: true }); } catch {}
process.exit(0);
