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
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: null };
  }
}

// One Api per page load. Each call returns a promise that is created once, so a second call for the same
// data (a project picked again, a range switched) fetches nothing.
export function createApi(fetcher = fetchJSON) {
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
    hasProject: (key) => perProject.has("usage:" + key) && perProject.has("settings:" + key),
  };
}
