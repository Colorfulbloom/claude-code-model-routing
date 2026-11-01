// The edit session. It holds the edit token for this tab, decides the edit mode and sends the three writes.
// No DOM here: everything it touches comes in through createEditSession, so node can test it with fakes.
//
// The printed link carries the token as #/settings?edit=<token>. take() is the one function that reads it.
// It strips the value from the address at once and keeps the token in sessionStorage (and in memory, so a
// blocked storage still works for this page load) beside the server's launch_id. The token is never logged
// and never goes into a URL; it travels only in the X-Dashboard-Token header of a POST.
//
// Modes: null (no answer from the server yet, or it never answered), "off" (edits are not enabled),
// "locked" (enabled, but this tab holds no valid token) and "ready" (a token that matches this launch).
//
// A write is a set (a value for a line, the default) or a remove (action "remove", the line goes and there is no value).

const TOKEN_KEY = "mr_edit_token";
const LAUNCH_KEY = "mr_edit_launch";

export function createEditSession({ api, storage, getHash, replaceHash, onChange, onWrite }) {
  let token = readStore(TOKEN_KEY);
  let launch = readStore(LAUNCH_KEY);
  let mode = null;
  let fresh = false;
  let taken = false;
  let seq = 0;

  function readStore(key) {
    try {
      const value = storage ? storage.getItem(key) : null;
      return typeof value === "string" && value !== "" ? value : null;
    } catch (err) {
      return null;
    }
  }

  function writeStore(key, value) {
    try {
      if (!storage) return;
      if (value === null) storage.removeItem(key);
      else storage.setItem(key, value);
    } catch (err) {
      // The in-memory copy still holds the value for this page load.
    }
  }

  function setToken(value) {
    token = value;
    writeStore(TOKEN_KEY, value);
  }

  function setLaunch(value) {
    launch = value;
    writeStore(LAUNCH_KEY, value);
  }

  function clearToken() {
    fresh = false;
    setToken(null);
    setLaunch(null);
  }

  function changed() {
    if (typeof onChange === "function") onChange();
  }

  // Removes edit= from the address and keeps every other query value and the route.
  function take() {
    const hash = String(getHash() || "");
    const raw = hash.replace(/^#/, "");
    const cut = raw.indexOf("?");
    if (cut < 0) return false;
    const path = raw.slice(0, cut);
    const pieces = raw.slice(cut + 1).split("&");
    let value = null;
    let found = false;
    const kept = [];
    for (const piece of pieces) {
      const eq = piece.indexOf("=");
      const name = eq < 0 ? piece : piece.slice(0, eq);
      let decoded = name;
      try {
        decoded = decodeURIComponent(name);
      } catch (err) {
        decoded = name;
      }
      if (decoded === "edit") {
        found = true;
        if (value === null && eq >= 0) {
          try {
            value = decodeURIComponent(piece.slice(eq + 1));
          } catch (err) {
            value = piece.slice(eq + 1);
          }
        }
      } else if (piece !== "") {
        kept.push(piece);
      }
    }
    if (!found) return false;
    replaceHash("#" + path + (kept.length ? "?" + kept.join("&") : ""));
    if (!value) return true;
    setToken(value);
    fresh = true;
    taken = true;
    return true;
  }

  async function refresh() {
    const mine = ++seq;
    let res = null;
    try {
      res = await api.editStatus();
    } catch (err) {
      res = null;
    }
    if (mine !== seq) return;
    if (!res || !res.ok || !res.data || typeof res.data !== "object") return;
    const before = mode;
    const wasTaken = taken;
    taken = false;
    if (res.data.enabled !== true) {
      clearToken();
      mode = "off";
    } else if (!token) {
      mode = "locked";
    } else if (fresh) {
      setLaunch(res.data.launch_id == null ? null : String(res.data.launch_id));
      fresh = false;
      mode = "ready";
    } else if (launch !== null && launch === String(res.data.launch_id)) {
      mode = "ready";
    } else {
      clearToken();
      mode = "locked";
    }
    if (mode !== before || wasTaken) changed();
  }

  // Sends one write and sorts the answer into an outcome.
  async function send(op, body, writes) {
    if (!token) return { kind: "locked", res: null };
    const res = await op(body, token);
    const code = res && res.data && typeof res.data === "object" ? res.data.error : null;
    if (code === "bad_token") {
      clearToken();
      mode = "locked";
      changed();
      return { kind: "locked", res };
    }
    if (code === "stale") return { kind: "stale", res };
    let kind = "error";
    if (res && res.ok) kind = "ok";
    else if (code === "raced") kind = "raced";
    else if (code === "unverified") kind = "unverified";
    // Only a save or an undo can change a file, so only they drop data. A preview never does.
    const dropped = writes && (kind === "ok" || kind === "raced" || kind === "unverified");
    if (dropped && typeof onWrite === "function") {
      try {
        await onWrite();
      } catch (err) {
        // The outcome is still the server's answer, whatever the reload did.
      }
    }
    return { kind, res };
  }

  return {
    take,
    refresh,
    mode: () => mode,
    // action "remove" sends the line to take out and no value. Any other action is a set, and sends what it always sent.
    preview: (project, target, value, action) =>
      send(api.editPreview, action === "remove" ? { project, target, action } : { project, target, value }, false),
    save: (project, preview, target, value, action) => {
      const base = preview && typeof preview === "object" ? preview : {};
      const hashes = { base_file: base.base_file, base_trail: base.base_trail, base_others: base.base_others };
      return send(api.editSave, action === "remove"
        ? { project, target, action, ...hashes }
        : { project, target, value, ...hashes }, true);
    },
    undo: (project, editId) => send(api.editUndo, { project, edit: editId }, true),
  };
}
