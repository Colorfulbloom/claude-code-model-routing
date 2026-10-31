// The match key of a trail entry, the same string dashboard/api_edit.py builds as ref_of(entry).
// A target or blocked row from /api/edit/targets carries it as `ref`, so the page can find the row
// an entry belongs to. The line is not part of it, because a minified file holds everything on one
// line, and file and path are compared as opaque strings. tests/fixtures/edit_ref_table.json runs
// under Python and under node, so the two builders cannot drift apart.

export function editRef(entry) {
  return JSON.stringify([entry.agent || "@main", entry.key, entry.layer, entry.file ?? null, entry.path || entry.key]);
}
