/*
 * The string deck for the M0 shell and gate pages. Values come from the tech-writer deck
 * (November 8) with the brand as "Bar Tab" where the brand is named (the narrator stays "the
 * dashboard"). Placeholders look like {name}. A key pair ending _one and _other is a plural,
 * read through tn(). The command is never a string. It comes from the bartab-command meta tag.
 */
export const en = {
  // Brand and shell
  product: "Bar Tab",
  project_label: "Project",
  project_aria: "Project, {name}",
  nav_aria: "Main",
  nav_live: "Live",
  nav_review: "Review",
  nav_summary: "Summary",
  nav_sessions: "Sessions",
  nav_agents: "Agents",
  nav_models: "Models",
  nav_setup_h: "Setup",
  nav_setup: "Your setup",
  nav_tofix: "To fix",
  nav_ref_h: "Reference",
  nav_decides: "How Claude Code decides",
  nav_glossary: "Glossary",
  nav_more: "More",
  nav_working: "Working",
  // To fix count, used in the accessible name of the nav item
  tofix_count: "{n}",
  tofix_aria_one: "To fix, {n} item",
  tofix_aria_other: "To fix, {n} items",
  updated_at: "Updated {time}",
  updated_never: "No answer yet",

  // Document titles and route status
  title_project: "{page}, {project}, Bar Tab",
  title_bare: "{page}, Bar Tab",
  title_locked: "Can't reach the dashboard, Bar Tab",
  title_stopped: "Dashboard stopped answering, Bar Tab",
  status_locked: "This tab can't reach the dashboard",
  status_stopped: "The dashboard stopped answering",

  // Locked page
  lk_h: "This tab can't reach the dashboard",
  lk_body_no_key:
    "This tab opened without a code, and no other dashboard tab answered to share one. Run this command in Claude Code to get a new link.",
  lk_body_code_used:
    "This link's code was already used. Each link works once. Run this command in Claude Code to get a new link.",
  lk_body_code_expired:
    "This link's code expired before the tab used it. Run this command in Claude Code to get a new link.",
  lk_body_code_unknown:
    "The dashboard didn't recognize this link's code. Run this command in Claude Code to get a new link.",
  lk_body_server_restarted:
    "The dashboard restarted, so this link no longer works. Run this command in Claude Code to get a new link.",
  lk_body_wrong_project_key:
    "This tab can't open this project with the link it has. Run this command in Claude Code to get a new link.",
  lk_route2: "This tab reopens on {page}, {project} once another tab opens the dashboard.",
  lk_tab_back: "Your other tab is open again on {page}, {project}.",
  lk_copy: "Copy command",
  cs_copied: "Copied to clipboard",
  hold_status: "Checking for another dashboard tab",

  // Server stopped
  stopped_h: "The dashboard stopped answering",
  stopped_body: "Run this command in Claude Code to start it again.",
  st_route: "When it answers, this tab goes back to {page}, {project} on its own.",
  st_retry: "Checking again every 10 seconds",
  st_last: "Last answer at {time}",
  stopped_try_now: "Try now",
  st_trying: "Checking",

  // First run
  fr_h: "Getting the dashboard ready",
  fr_body:
    "The dashboard sets itself up the first time it runs. The last step saves your past Claude Code sessions, so Review keeps them after Claude Code deletes old ones.",
  fr_s1: "Download Python",
  fr_s2: "Install the dashboard's packages",
  fr_s3: "Read your usage history",
  fr_done: "Done",
  fr_now: "In progress",
  fr_next: "Next",
  fr_counting: "Counting files",
  fr_size: "{d} of {t}",
  fr_local: "This step reads files on this computer, so it doesn't need an internet connection.",
  fr_failed: "Failed",
  fr_fail_h: "The dashboard couldn't finish setting up",
  fr_fail_config_dir_missing:
    "The dashboard can't find Claude Code's projects folder, where Claude Code keeps session transcripts.",
  fr_fail_config_dir_unreadable:
    "The dashboard isn't allowed to read {file}. Check that folder's permissions.",
  fr_fail_store_unwritable:
    "The dashboard can't save to {file}. Check that the disk has space and the folder allows writing.",
  fr_fail_store_damaged: "The dashboard's database at {file} failed its integrity check.",
  fr_fail_unexpected: "Something unexpected stopped this step. The details are in {file}.",
  fr_fail_fix: "Run this command in Claude Code to try again.",
  fr_fail_fix2:
    "The dashboard tries again on its own. To try now, run this command in Claude Code.",
  fr_next_try: "Next try at {t}",

  // A store written by a newer Bar Tab
  sn_h: "This history needs a newer Bar Tab",
  sn_body:
    "A newer Bar Tab upgraded your saved history, so Bar Tab {old}, the version running now, can't open it.",
  sn_next: "Update Bar Tab, then run this command in Claude Code.",

  // Sidebar footer
  ft_updated: "Updated {t}",
  ft_since: "History since {d}",
  ft_backup: "Last backup {t}",
  ft_prices: "Prices as of {d}",
  ft_prices_bundled: "Bundled prices, {d}",
  ft_prices_saved: "Saved prices, {d}",
  ft_prices_custom: "Custom prices",
  ft_backup_failed: "Backup failed at {t}",
  ft_unreadable_one: "Couldn't read {n} file",
  ft_unreadable_other: "Couldn't read {n} files",

  // Updates stopped notice, one sentence per code
  nt_stopped_config_dir_missing:
    "Updates stopped at {t} because the dashboard couldn't find Claude Code's projects folder, and it keeps trying again on its own.",
  nt_stopped_config_dir_unreadable:
    "Updates stopped at {t} because the dashboard couldn't read {f}, and it keeps trying again on its own.",
  nt_stopped_store_unwritable:
    "Updates stopped at {t} because the dashboard couldn't save to {f}, and it keeps trying again on its own.",
  nt_stopped_store_damaged:
    "Updates stopped at {t} because the database at {f} failed its integrity check, and the dashboard keeps trying again on its own.",
  nt_stopped_store_newer:
    "Updates stopped at {t} because a newer Bar Tab upgraded your saved history, so update Bar Tab to bring them back.",
  nt_stopped_unexpected:
    "Updates stopped at {t} after something unexpected went wrong, so the dashboard wrote the details to {f} and keeps trying.",
  nt_stopped_nofile: "a file",

  // More page
  more_h1: "More",
  more_ver_h: "Version",
  more_ver_cc: "Claude Code {version}",
  more_ver_app: "Bar Tab {version}",
  more_hist_h: "Your history",
  more_l_updated: "Updated",
  more_l_since: "History since",
  more_l_backup: "Last backup",
  more_l_prices: "Prices as of",
  more_prices_bundled: "Bundled prices, {d}",
  more_prices_saved: "Saved prices, {d}",
  more_prices_custom: "Custom prices",
  mb_backup_no_space:
    "The disk was full, so the backup didn't finish. Your saved history isn't affected, and the dashboard keeps your last seven good backups.",
  mb_backup_unwritable:
    "The dashboard couldn't write to its backup folder, so the backup didn't finish. Your saved history isn't affected.",
  mb_backup_check_failed:
    "The new backup failed its check, so the dashboard threw it away. Your saved history isn't affected.",
  mb_backup_copy_failed:
    "The dashboard couldn't copy your history, so the backup didn't finish. Your saved history isn't affected.",
  mb_backup_newest: "The newest good backup is from {d}.",
  mb_unread_b:
    "Requests in these files aren't counted yet, but the rest of your history is. The dashboard tries these files again on its next pass.",

  // Project picker
  pk_h: "Projects",
  pk_state_ok: "Ready",
  pk_state_no_claude_folder: "No .claude folder",
  pk_state_folder_not_found: "Folder not found",
  pk_running: "Agent working",
  pk_st_noclaude_d: "Opens with its usage and your user setup, without project settings.",
  pk_st_notfound_d:
    "Nothing is at this path now, so it opens with usage history but no project setup.",
  pk_empty_h: "No projects yet",
  pk_empty: "A project appears here after you use Claude Code in it.",
  pk_close: "Close",
  pk_loading: "Loading projects",
  pk_placeholder: "Pick a project",

  // Placeholder pages
  ph_body: "This page comes in a later release.",
  pg_session: "Session",
  pg_agent_new: "New agent",
  pg_agent_edit: "Edit agent",
  pg_surface: "Setup item",
  pg_surface_edit: "Edit setup item",
} as const;

export type StringKey = keyof typeof en;
