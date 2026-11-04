// The Live page's poller. It asks /api/live every few seconds while the page is active, the tab is in view and the
// page is not paused, and tells the page what came back. Timers and the tab's visibility are passed in, so a node
// check can drive it with fake ones.
//
//   POLL_MS    wait between two requests while answers arrive
//   RETRY_MS   wait between two requests while the server does not answer
//
// The poller never has two requests in flight. It sends session=<shown id> after the first answer (the choice sticks
// until the page picks another one or the server says the session is gone) and the etag of the last full answer, so
// an unchanged answer is small. A 4xx answer ends in "unknown" and the poller stops, because asking again cannot help.
// Status 0, a 5xx or a body that will not parse ends in "lost", and the poller tries again every RETRY_MS.
//
// onAnswer({ data, unchanged }) is called for every good answer. onState(mode) is called when the mode changes:
// "ok", "lost" or "unknown".

export const POLL_MS = 1000; // one /api/live call takes about 7 ms (30 ms after a change) with 300 transcript files
export const RETRY_MS = 10000;

export function createLivePoller({ fetchLive, setTimer, clearTimer, isVisible, onAnswer, onState }) {
  let active = false;
  let paused = false;
  let mode = "ok";
  let inFlight = false;
  let timer = null;
  let generation = 0;
  let session = null;
  let etag = null;

  const wanted = () => active && !paused && isVisible() && mode !== "unknown";

  function stopTimer() {
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }
  }

  function schedule() {
    stopTimer();
    if (!wanted() || inFlight) return;
    timer = setTimer(() => { timer = null; poll(); }, mode === "lost" ? RETRY_MS : POLL_MS);
  }

  function setMode(next) {
    if (next === mode) return;
    mode = next;
    onState(next);
  }

  function valid(res) {
    return Boolean(res && res.ok && res.data && typeof res.data === "object" && !Array.isArray(res.data));
  }

  function settle(res) {
    if (valid(res)) {
      const data = res.data;
      if (data.unchanged === true) {
        setMode("ok");
        onAnswer({ data, unchanged: true });
        return;
      }
      etag = typeof data.etag === "string" ? data.etag : null;
      const shown = data.session && typeof data.session === "object" ? data.session.session_id : null;
      session = typeof shown === "string" ? shown : null;
      setMode("ok");
      onAnswer({ data, unchanged: false });
      return;
    }
    const status = res ? res.status : 0;
    if (status >= 400 && status < 500) setMode("unknown");
    else setMode("lost");
  }

  function poll() {
    stopTimer();
    if (inFlight) return;
    inFlight = true;
    const mine = generation;
    let pending;
    try {
      pending = Promise.resolve(fetchLive(session, etag));
    } catch (err) {
      pending = Promise.resolve({ ok: false, status: 0, data: null });
    }
    pending.catch(() => ({ ok: false, status: 0, data: null })).then((res) => {
      inFlight = false;
      try {
        if (mine === generation) settle(res);
      } finally {
        // A reset while this request was out: its answer is for the old project, so ask again for the new one.
        // The finally keeps the polling going even when drawing the answer throws.
        if (mine !== generation && wanted()) poll();
        else schedule();
      }
    });
  }

  return {
    // The page is the visible section (on) or not (off). On: ask at once.
    setActive(on) {
      if (on === active) return;
      active = on;
      if (on && wanted()) poll();
      else stopTimer();
    },
    setPaused(on) {
      if (on === paused) return;
      paused = on;
      if (on) stopTimer();
      else if (wanted()) poll();
    },
    // The tab went into view or out of it.
    visibilityChanged() {
      if (isVisible() && wanted()) poll();
      else stopTimer();
    },
    // Try now: one request at once, whatever the wait.
    tryNow() {
      if (active && !paused && isVisible()) {
        if (mode === "unknown") mode = "lost";
        poll();
      }
    },
    // The viewer picked another session. Forget the etag, because it belongs to the old one.
    setSession(id) {
      generation += 1; // an answer still on its way is for the old session
      session = id || null;
      etag = null;
      if (wanted()) poll();
    },
    // A different project: forget the session, the etag and any error, and ask at once for the new one.
    reset(id = null) {
      generation += 1;
      session = id || null;
      etag = null;
      const was = mode;
      mode = "ok";
      if (was !== "ok") onState("ok");
      stopTimer();
      if (wanted()) poll();
    },
    session: () => session,
    etag: () => etag,
    mode: () => mode,
    busy: () => inFlight,
  };
}
