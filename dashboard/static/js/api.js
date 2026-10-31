// Fetch wrappers and the in-memory cache. A request never throws: it resolves to
// { ok, status, data }. A route the server does not have yet (404), a refusal (400 for the
// "all" project on /api/settings) and a network error all come back with ok false and data null,
// so the page that wanted the data keeps showing its stub.

export async function fetchJSON(path) {
  try {
    const res = await fetch(path, { headers: { Accept: "application/json" }, credentials: "same-origin" });
    let data = null;
    if (res.ok) {
      try {
        data = await res.json();
      } catch (err) {
        return { ok: false, status: res.status, data: null };
      }
    } else {
      // Read the error body too, or the response never finishes and the browser keeps it open.
      try {
        await res.text();
      } catch (err) {
        // Nothing here is kept, so a body that won't read changes nothing.
      }
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: null };
  }
}

// A POST with the edit token. Like fetchJSON it never throws, but it parses the body on an error status too,
// because the error code (bad_token, stale, raced, unverified) is in it. A body that won't parse gives data null.
export async function postJSON(path, body, token) {
  try {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-Dashboard-Token": token || "" },
      body: JSON.stringify(body),
    });
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      data = null;
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: null };
  }
}

// One Api per page load. Each call returns a promise that is created once, so a second call for the same
// data (a project picked again, a range switched) fetches nothing.
export function createApi(fetcher = fetchJSON, poster = postJSON) {
  const shared = new Map();
  const perProject = new Map();

  function once(map, key, path) {
    if (!map.has(key)) {
      const promise = fetcher(path);
      map.set(key, promise);
      // A network error (status 0) or a 5xx is not kept, so the next call asks again. A 4xx stays,
      // because 404 is the normal answer for a route the server does not have yet.
      promise.then((res) => {
        const keep = res && (res.ok || (res.status >= 400 && res.status < 500));
        if (!keep && map.get(key) === promise) map.delete(key);
      });
    }
    return map.get(key);
  }

  function projectQuery(key) {
    return "?project=" + encodeURIComponent(key);
  }

  return {
    strings: () => once(shared, "strings", "/static/strings.json"),
    projects: () => once(shared, "projects", "/api/projects"),
    rules: () => once(shared, "rules", "/api/rules"),
    files: () => once(shared, "files", "/api/files"),
    usage: (key) => once(perProject, "usage:" + key, "/api/usage" + projectQuery(key)),
    settings: (key) => once(perProject, "settings:" + key, "/api/settings" + projectQuery(key)),
    // True once both of a project's payloads were asked for.
    // The edit routes never go through the cache, so a save is never followed by an old answer.
    editStatus: () => fetcher("/api/edit"),
    editTargets: (key) => fetcher("/api/edit/targets" + projectQuery(key)),
    editHistory: (key) => fetcher("/api/edit/history" + projectQuery(key)),
    editPreview: (body, token) => poster("/api/edit/preview", body, token),
    editSave: (body, token) => poster("/api/edit/save", body, token),
    editUndo: (body, token) => poster("/api/edit/undo", body, token),
    // Forgets every project's usage: and settings: answer. The shared keys stay.
    dropProjects: () => { perProject.clear(); },
    hasProject: (key) => perProject.has("usage:" + key) && perProject.has("settings:" + key),
  };
}
