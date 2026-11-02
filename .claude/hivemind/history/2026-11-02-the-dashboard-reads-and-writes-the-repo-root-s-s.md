### F-bd91 The dashboard reads and writes the repo root's settings.local.json, repo lock off (#104)
status: shipped
kind: code
dates: 2026-11-02 .. 2026-11-02
refs:
  commit: 057353e45d48f0999c737001cacc96adfcd770e0 (branch feature/104-repo-root, merged into development)
summary: Local file targets the repo root (main checkout for a worktree, submodule top for a submodule); the starting folder's leftover file is read-only with undo kept; lock only when the root can't be worked out.
decisions:
- One helper, dashboard/local_root.py for_project, gives the local path for collect, target_for and overlays; worked out once per request and kept on the view.
- repo_root parses .git files with no process (lstat, O_NOFOLLOW and O_NONBLOCK, 4 KiB cap) and accepts a worktree only with the inode match and the back link; anything odd reads unknown and locks.
- Save's plan raises stale "file" when the fresh target path differs; the trail hash carries the local file, because api_edit target ids hold no path.
- start_local blocks carry no blocked_ids entry, since the leftover and root share an id.
- The walk is bounded by ctx.root before any .git file is read, so fixture runs and test worlds never reach a real repo; helpers._tmp_base refuses a base inside a work tree.
- Version rule in local_root: Claude Code below 2.1.211 keeps the starting folder; an unknown version assumes the root.
- Two local files deep-merge with the root on top, backed by harness probes (nested modelSettings, submodule subfolder, separate git dir, root is HOME).
- A bare repo named .git is refused: repo_root reads the common dir's config (64 KiB cap, same safe open), and core.bare true reads unknown and locks. A missing config is not bare, because hand-made test worktrees have none.
- The local row shows the note "Leftover local file, read-only" (ed_row_lock_start_local, edit_card.js) when a worktree's leftover local file holds the winning value (owner's choice, November 2).
rejected:
- rev-parse per request: a child process on every Settings load, needs the binary on PATH, reads repo config.
- Target ids that hash the path: would change the page's opaque ids; a path check in the plan does the job.
- Bounding only the result by ctx.root: still read .git files above a fixture, so the bound moved into the walk.
files: dashboard/local_root.py, dashboard/git_check.py, dashboard/collect.py, dashboard/api_settings.py, dashboard/edit_store.py, dashboard/api_edit.py, dashboard/static/strings.json, dashboard/static/js/edit_review.js, dashboard/static/js/pages/settings.js, dashboard/experiments/harness/runcase.py, tests/helpers.py, tests/test_local_root.py, tests/test_edit_e2e_repo_root.py
gotchas:
- The page never renders the targets payload's blocked list; a winning leftover line shows as the local row's note, plus the trail and limits.
- Any test double for repo_root must accept (path, home=None, bound=None).
- tests/test_edit_security.py proves an os.open read-only only when its flags are a module-level constant.
- The page E2E first waited for the saved strip's backup path after a create; a create keeps only an .absent marker, so no path renders (U-ea51). Test fixed to wait for the line and Undo and to assert no path.
follow-ups:
- Owner runs MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p "test_edit_e2e_repo_root.py".
- HiveMind proposals decided in the November 2 consolidation (G-c2d7, N-e2fd).
