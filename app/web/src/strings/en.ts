/*
 * The string deck for the M0 shell and gate pages, plus the M4 Setup deck (tech-writer, November
 * 10, owner review pending). Values come from the tech-writer deck
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

  // Live (M2). Board words from strings.js and strings-m2.js (tech-writer, November 8 and 9),
  // with the owner's copy answers of November 9 (m2-build.md section 13). The demo project's
  // name and folder became {project} and {path}.
  lv_h1: "Live",
  lv_sub_live: "{project}, started {start}, {dur} so far",
  lv_sub_ended: "{project}, started {start}, {dur} in all",
  lv_no_branch: "No git branch",
  lv_paused_at: "Paused at {time}",
  lv_lost_at: "Last reached the server at {time}",
  lv_ended_at: "Ended at {time}",
  lv_pause: "Pause",
  lv_resume: "Resume",
  lv_demo: "Demo data",
  lv_loading: "Loading this session",
  rs_working: "Working",
  rs_finished: "Finished",
  rs_idle: "Idle",
  rs_not_started: "Not started yet",
  rs_ended: "Ended",
  lost_h: "Can't reach the Bar Tab server",
  lost_b: "These numbers are from {time}. Bar Tab tries again every 10 seconds.",
  lost_try: "Try now",

  // Live tiles
  t_cost: "Spent so far",
  t_cost_ended: "Spent in all",
  t_cost_d: "{cost} in the last minute",
  t_cost_kx: "API-rate estimate",
  t_unpriced_one: "{n} request has no price",
  t_unpriced_other: "{n} requests have no price",
  t_tokens: "Tokens",
  t_tokens_d: "{tokens} in the last minute",
  t_cache: "Read from cache",
  t_cache_d: "{pct} in the last minute",
  t_agents: "Agents working",
  t_agents_ended: "Agent runs",
  t_agents_d: "{finished} finished, {runs} runs in all",
  t_agents_ended_d: "All finished",
  t_agents_more: "+{n}",
  t_ended_d: "Whole session",

  // Who is working
  tl_h: "Who is working",
  tl_q: "Each row is one agent run, placed by when it ran",
  tl_axis_lab: "New tokens per minute",
  tl_axis_avg: "New tokens per minute, averaged over {n} minutes",
  tl_now: "Now",
  tl_main: "Main session",
  tl_last: "Last request {n} s ago",
  tl_last_min: "Last request {n} min ago",
  tl_ran: "Ran {n} min",
  tl_round: "Round {n}",
  tl_unl_may: "Finding starter",
  tl_unl_never: "No starter found",
  tl_by: "Started by {name}",
  tl_fold: "{n} finished earlier",
  tl_fold_show: "Show",
  tl_fold_hide: "Hide",
  tl_note:
    "Indented rows were started by the row above them, and a dashed line means the starter isn't known. Bars that reach Now are still working.",
  c_least: "at least {cost}",
  c_none: "No price for {model}",
  c_none_short: "No price",

  // Model check
  mc_h: "Model check",
  mc_q: "Did each agent run on the model and effort it's set to?",
  mc_ok_one: "The other agent ran as set.",
  mc_ok_other: "The other {n} agents ran as set.",
  mc_all_ok_one: "The agent ran as set.",
  mc_all_ok_other: "All {n} agents ran as set.",

  // Latest requests
  rq_h: "Latest requests",
  rq_q: "What did each request cost?",
  rq_time: "Time",
  rq_agent: "Agent",
  rq_model: "Model",
  rq_tokens: "Tokens",
  rq_cost: "Cost",
  rq_f_disagree: "Two price sources disagree on {model}, so its costs may be off.",

  // Session switching and empty states
  nt_switch: "A new session started on {branch} at {time}.",
  nt_switch_btn: "Switch to it",
  nr_h: "Nothing is running in {project}",
  nr_b: "A session shows here as soon as Claude Code sends a request in this project. This page checks every 5 seconds.",
  nr_last: "Open the last session",
  nr_last_meta: "{branch}, ended {time}",
  nr_other_h: "Running in other projects",
  nr_other_q: "Each one opens that project's Live page",
  ns_h: "No sessions in {project} yet",
  ns_b: "Start Claude Code in the project folder. Its first request shows here within a few seconds.",
  gone_h: "This session isn't in {project}",
  gone_b: "The link names a session Bar Tab can't find in this project.",
  gone_open: "Open the running session",
  gone_all: "See all sessions",

  // Session Select
  sel_label: "Session",
  sel_none: "None running",
  sel_pick: "Pick a session",
  ss_h: "Sessions",
  ss_this: "This project",
  ss_other: "Other projects",
  ss_all: "See all sessions",
  ss_opt: "{branch}, {time}",

  // Announcements, polite, state changes only
  an_start: "{name} started",
  an_start_by: "{name} started by {parent}",
  an_finish: "{name} finished",
  an_finish_moved: "{name} finished, started by {parent}",
  an_round: "{name} started round {n}",
  an_ended: "Session ended at {time}",
  an_resumed: "Session is working again",
  an_batch: "{list} finished",
  an_paused: "Updates paused",
  an_resumed_poll: "Updates resumed",
  // Model check titles and reasons, tech-writer draft of November 9 (owner review pending).
  // mc_nofile_list groups agents with no file into one line (lead, from mc_r_no_agent_file).
  mc_t_in_effect: "{agent} ran as set",
  mc_r_in_effect: "{file} line {line} sets its {setting} to {value}, and its runs used it.",
  mc_r_in_effect_nofile: "Its {setting} is set to {value}, and its runs used it.",
  mc_t_default: "{agent} ran on the default {setting}",
  mc_r_default: "{file} line {line} sets {value}, which is Claude Code's built-in default.",
  mc_r_default_nofile:
    "Nothing sets its {setting}, so Claude Code's built-in default of {value} applies.",
  mc_t_lowered_by_cap: "{agent} ran at {ran}",
  mc_t_lowered_by_cap_model: "{agent} ran on {ran}",
  mc_r_lowered_by_cap:
    "{file} line {line} sets {value}, but the {setting} cap in {cap_file} line {cap_line} lowers it to {expected}.",
  mc_r_lowered_by_cap_nocapfile:
    "{file} line {line} sets {value}, but the {cap_key} cap of {cap_value} lowers it to {expected}.",
  mc_r_lowered_by_cap_nofile:
    "It's set to {value}, but the {setting} cap in {cap_file} line {cap_line} lowers it to {expected}.",
  mc_r_lowered_by_cap_nofile_nocapfile:
    "It's set to {value}, but the {cap_key} cap of {cap_value} lowers it to {expected}.",
  mc_t_lowered_ran_at_pin: "{agent} ran at {ran} despite the cap",
  mc_t_lowered_ran_at_pin_model: "{agent} ran on {ran} despite the cap",
  mc_r_lowered_ran_at_pin:
    "The {setting} cap in {cap_file} line {cap_line} should lower {value} to {expected}, but its runs still used {ran}.",
  mc_r_lowered_ran_at_pin_nocapfile:
    "The {cap_key} cap of {cap_value} should lower {value} to {expected}, but its runs still used {ran}.",
  mc_t_pin_overridden: "{agent} gets its {setting} from {by_layer}",
  mc_r_pin_overridden:
    "Its file sets {value} in {file} line {line}, but {by_key} in {by_file} line {by_line} wins with {expected}.",
  mc_r_pin_overridden_nobyfile:
    "Its file sets {value} in {file} line {line}, but {by_key} in {by_layer} wins with {expected}.",
  mc_r_pin_overridden_nofile:
    "Its file sets {value}, but {by_key} in {by_file} line {by_line} wins with {expected}.",
  mc_r_pin_overridden_via: "Its file sets {value}, but {by_via} wins with {expected}.",
  mc_t_pin_ignored: "Claude Code ignores {agent}'s {setting}",
  mc_r_pin_ignored:
    "Its file sets {value} in {file} line {line}, but Claude Code doesn't read that setting here.",
  mc_r_pin_ignored_exp:
    "Its file sets {value} in {file} line {line}, but Claude Code doesn't read it here, so {expected} applies.",
  mc_r_pin_ignored_nofile: "Its file sets {value}, but Claude Code doesn't read that setting here.",
  mc_t_pin_invalid: "{agent} has an invalid {setting}",
  mc_r_pin_invalid:
    "Its file sets {value} in {file} line {line}, but Claude Code doesn't accept it. Its runs used {ran}.",
  mc_r_pin_invalid_nofile:
    "Its file sets {value}, but Claude Code doesn't accept it. Its runs used {ran}.",
  mc_t_expected_unknown: "Bar Tab can't check {agent}'s {setting}",
  mc_r_expected_unknown:
    "{file} line {line} sets {value}, but Bar Tab can't tell which setting wins. Its runs used {ran}.",
  mc_r_expected_unknown_nofile:
    "Bar Tab can't tell which {setting} setting wins. Its runs used {ran}.",
  mc_t_unknown_status: "{agent} has a result Bar Tab doesn't know",
  mc_r_unknown_status: "Bar Tab can't read this result for its {setting}. Its runs used {ran}.",
  mc_t_ran_differs: "{agent} ran at {ran}, not {expected}",
  mc_t_ran_differs_model: "{agent} ran on {ran}, not {expected}",
  mc_r_ran_differs: "It's set to {expected}, but its runs used {ran}.",
  mc_t_ran_mixed: "{agent}'s runs used different {setting} values",
  mc_r_ran_mixed: "It's set to {expected}, but its runs used {ran}, most common first.",
  mc_t_no_agent_file: "{agent} has no agent file",
  mc_r_no_agent_file: "Bar Tab found no agent file for it, so there's nothing to check.",
  mc_nofile_list: "{list} have no agent file, so there's nothing to check.",
  mc_t_unnamed_agent: "Runs with no agent type",
  mc_r_unnamed_agent: "These runs don't name an agent type, so Bar Tab can't match them to a file.",
  mc_t_no_pin: "{agent} sets no model or effort",
  mc_r_no_pin: "Its file sets neither model nor effort, so there's nothing to check.",
  mc_r_no_pin_main: "Your settings set neither model nor effort, so there's nothing to check.",
  // One-line findings for the compact Review card (tech-writer, November 9, from the board).
  mc_l_pin_overridden: "{agent} ran at {ran}, but its file sets {value}.",
  mc_l_pin_overridden_model: "{agent} ran on {ran}, but its file sets {value}.",
  mc_l_ran_differs: "{agent} ran at {ran}, but it's set to {expected}.",
  mc_l_ran_differs_model: "{agent} ran on {ran}, but it's set to {expected}.",
  mc_l_lowered_by_cap:
    "{agent} ran at {expected}, because the {setting} cap lowers the {value} it's set to.",
  mc_l_lowered_by_cap_model:
    "{agent} ran on {expected}, because the {setting} cap lowers the {value} it's set to.",
  status_in_effect: "In effect",
  status_overridden: "Overridden",
  status_ignored: "Ignored",
  status_lowered: "Lowered",
  status_invalid: "Invalid",
  status_default: "Default",
  status_unknown: "Unknown",
  dur_under_min: "less than a minute",
  dur_min_one: "{n} minute",
  dur_min_other: "{n} minutes",
  dur_hr_one: "{n} hour",
  dur_hr_other: "{n} hours",
  dur_hr_min: "{hours} {minutes}",
  list_and: "{list} and {last}",
  // M3 Review. Values from strings-m3.js and the task 8 deck (tech-writer, November 9), with the
  // owner's copy decisions of November 9. Board names became {project}, {range} and {when}.
  // Range Select, scope bar and route status
  rg_h: "Range",
  rg_today: "Today",
  rg_7d: "Last 7 days",
  rg_30d: "Last 30 days",
  rg_90d: "Last 90 days",
  rg_12m: "Last 12 months",
  rg_all: "All time",
  rg_w_today: "Midnight to {time}",
  rg_w_span: "{start} to {end}",
  rg_w_all: "Since {date}",
  rg_p_today: "today",
  rg_p_days: "in the last {n} days",
  rg_p_12m: "in the last 12 months",
  rg_p_all: "since {date}",
  rg_n_today: "today",
  rg_n_days: "the last {n} days",
  rg_n_12m: "the last 12 months",
  rg_n_all: "everything since {date}",
  rt_range: "Showing {range}",
  sub_today: "Today to {time}, compared with yesterday to {time}",
  sub_span: "{start} to {end}, compared with the {n} days before",
  sub_short:
    "{start} to {end}. Records start on {date}, so there's nothing earlier to compare with.",
  sub_all: "Everything recorded since {date}",
  // Review tiles
  rv_t_cost: "Cost",
  rv_t_sessions: "Sessions",
  rv_t_tokens: "Tokens",
  rv_t_cache: "Read from cache",
  t_up: "Up {p} from {v}",
  t_down: "Down {p} from {v}",
  t_same: "Little change from {v}",
  t_up_n: "Up from {v}",
  t_down_n: "Down from {v}",
  t_up_pt: "Up {p} points from {v}",
  t_down_pt: "Down {p} points from {v}",
  t_yday: "{v} yesterday by {time}",
  t_avg_cost: "{v} a day on average",
  t_avg_sessions: "{v} a day on average",
  t_avg_tokens: "{v} a day on average",
  t_avg_cache: "Across every request",
  t_avg_cache_range: "Across the whole range",
  // Cost chart
  ch_h_hour: "Cost per hour",
  ch_h_day: "Cost per day",
  ch_h_week: "Cost per week",
  ch_h_month: "Cost per month",
  ch_q: "Which models did the spending?",
  ch_win_today: "Today to {time}",
  ch_win_day: "{date}",
  ch_win_span: "{start} to {end}",
  ch_prev_aria: "Show earlier costs, {window}",
  ch_next_aria: "Show later costs, {window}",
  ch_none_earlier: "Nothing earlier. Records start on {date}.",
  ch_none_later: "Nothing later yet",
  ch_norec: "No records before {date}",
  ch_now: "Now",
  ch_kinds: "Made of",
  ch_kinds_link: "See what each model's cost is made of",
  ch_unpriced_one: "{n} request on {model} has no price, so it's left out of these bars.",
  ch_unpriced_other: "{n} requests on {model} have no price, so they're left out of these bars.",
  ch_legend_least: "at least {v}",
  ch_img_hour: "Bar chart of cost per hour for {window}, {total} in all, most of it on {model}",
  ch_img_day: "Bar chart of cost per day for {window}, {total} in all, most of it on {model}",
  ch_img_week: "Bar chart of cost per week for {window}, {total} in all, most of it on {model}",
  ch_img_month: "Bar chart of cost per month for {window}, {total} in all, most of it on {model}",
  ch_img_none: "Bar chart for {window} with no cost to show",
  ch_scope_note: "The tiles above still cover {range}.",
  pager_prev: "Earlier",
  pager_next: "Later",
  pager_newest: "Back to newest",
  foot_est: "Costs are estimates at API list prices, not your bill. Prices as of {date}.",
  foot_disagree: "Two price sources disagree on {model}, so its costs may be off.",
  k_input: "Input",
  k_output: "Output",
  k_cache_read: "Cache read",
  k_cache_write: "Cache write",
  kind_legend_note: "Patterns show the kind of cost. Colors show the model.",
  // Summary cards
  rv_who_h: "Where the money went",
  rv_who_q: "Which agents cost the most?",
  rv_chk_h: "Model check",
  rv_top_h: "Most expensive sessions",
  rv_top_q: "Open one to replay it",
  mc_sum_n_one: "{k} of {n} agent didn't run as set",
  mc_sum_n_other: "{k} of {n} agents didn't run as set",
  mc_ok_rest_one: "The other agent ran as set.",
  mc_ok_rest_other: "The other {n} agents ran as set.",
  top_all_one: "See {n} session",
  top_all_other: "All {n} sessions",
  // Sessions
  ss_col_session: "Session",
  ss_col_cost: "Cost",
  ss_col_tokens: "Tokens",
  ss_col_runs: "Runs",
  // Task 21 item 10, reviewed by tech-writer November 10. The visible note under the
  // Agents and Sessions tables.
  runs_def: "Runs counts each agent run, plus one for the main session in each session.",
  ss_col_agents: "Agents",
  ss_page: "Showing {a} of {n}",
  ss_more_one: "Show {n} more",
  ss_more_other: "Show {n} more",
  ss_today: "Today",
  ss_yday: "Yesterday",
  ss_before: "Started earlier",
  ss_before_aria: "Started before this range. The cost shown is only the part inside it.",
  ss_end_one: "That's the only session",
  ss_end_other: "That's all {n} sessions",
  // Agents
  ag_h: "Agents",
  ag_q: "Every agent that ran in this range, and agent files that didn't run",
  ag_col_agent: "Agent",
  ag_col_set: "Set to",
  ag_col_ran: "Ran with",
  ag_col_check: "Check",
  ag_col_runs: "Runs",
  ag_col_cost: "Cost",
  ag_src_user: "User",
  ag_src_project: "Shared project",
  ag_main_src: "Settings",
  ag_src_none: "No agent file",
  ag_src_unnamed: "Runs with no agent type",
  ag_src_unknown: "Source unknown",
  ag_src_unknown_aria: "Bar Tab found no user or project file for this agent type.",
  ag_unnamed: "Unnamed agent",
  ag_nothing: "Nothing set",
  ag_set_failed: "Couldn't read its setup",
  ag_setup_card: "agent setup",
  ag_also_one: "Also {setup} on {n} run",
  ag_also_other: "Also {setup} on {n} runs",
  ag_none_h: "No runs in this range",
  // Models
  md_h: "Models",
  md_q: "What each model cost, and what the cost is made of",
  md_col_model: "Model",
  md_col_cost: "Cost",
  md_col_share: "Share",
  md_col_tokens: "Tokens",
  md_col_cache: "From cache",
  md_col_used: "Used by",
  md_kind_h: "What the cost is made of",
  md_kind_q: "Which kind of cost was the biggest?",
  md_img:
    "Chart of what each model's cost is made of for {window}, {total} in all, most of it on {model}",
  md_img_none:
    "Chart of what each model's cost is made of for {window}, with no priced cost to show",
  // Review card states
  ld_line: "Loading {card}",
  er_h: "Couldn't load {card}",
  er_b: "The Bar Tab server sent an error for this card. The rest of the page is fine.",
  er_try: "Try again",
  cd_stale: "Updated {time}. The latest refresh failed.",
  em_h: "No sessions in {project} {range}",
  em_b: "The last one ran {when}. A new session shows here once Claude Code sends a request in this project.",
  em_when_today: "today at {time}",
  em_when_yday: "yesterday at {time}",
  em_when_date: "on {date} at {time}",
  em_a: "Show the last 7 days",
  em_live: "Open Live",
  // Session review
  rv_open_live: "Open in Live",
  rv_session_scope: "Session",
  sr_back: "Sessions {range}",
  sr_sub_ended: "{project}, {date}, {start} to {end}, {dur}",
  sr_sub_running: "{project}, started {start}, still running",
  sr_tl_h: "Who worked when",
  sr_showing: "Showing",
  sr_at_now: "Now",
  sr_to_end: "Go to end",
  sr_to_now: "Back to now",
  sr_keys: "Arrow keys move 1 minute, Page Up and Page Down move {n}",
  sr_label: "Replay time",
  sr_prec_long: "On long sessions they update every {n} minutes, but runs update every minute.",
  sr_note:
    "Drag the line, or use the arrow keys, to replay the session minute by minute. Hollow bars show work that comes after the line.",
  sr_since: "Since {time}",
  sr_ran: "Ran {n} min",
  sr_later_one: "{n} starts later",
  sr_later_other: "{n} start later",
  sr_later_show: "Show",
  sr_later_hide: "Hide",
  sr_later_show_aria_one: "Show {n} run that starts later under {name}",
  sr_later_show_aria_other: "Show {n} runs that start later under {name}",
  sr_later_hide_aria_one: "Hide {n} run that starts later under {name}",
  sr_later_hide_aria_other: "Hide {n} runs that start later under {name}",
  sr_img:
    "Chart of new tokens per minute from {start} to {time}, {total} in all, most of them on {model}",
  sr_img_avg:
    "Chart of new tokens per minute, averaged over {n} minutes, from {start} to {time}, {total} in all, most of them on {model}",
  sr_sum: "At {time}, {w} working, {f} finished and {s} not started yet. {cost} spent so far.",
  c_not_started: "Not started yet",
  t_at_cost: "Spent by {time}",
  t_at_tokens: "Tokens by {time}",
  t_at_cache: "Read from cache by {time}",
  t_at_runs: "Runs by {time}",
  t_of_cost: "{v} in the whole session",
  t_of_tokens: "{v} in the whole session",
  t_of_cache: "{v} for the whole session",
  t_of_runs_one: "{w} working, {n} not started yet",
  t_of_runs_other: "{w} working, {n} not started yet",
  t_of_runs_w_one: "{n} working",
  t_of_runs_w_other: "{n} working",
  t_whole: "Whole session",
  t_sofar: "Whole session so far",
  t_runs: "Runs",
  t_runs_d_one: "{n} finished",
  t_runs_d_other: "{n} finished",
  sel_h: "Sessions {range}",
  sel_value: "{day}, {time}",
  sel_all_one: "See {n} session",
  sel_all_other: "See all {n} sessions",
  gone_title: "Session not found",

  // Setup (M4). Values from the M4 string deck (tech-writer, November 10, owner review pending).
  // Keys that end in a server code (sl_, hk_ev_, pc_, rs_, fx_cant_, ro_) are looked up directly
  // by that code, and sl_ and hk_ev_ keep Claude Code's camelCase spelling. {where} is built from
  // loc_line or loc_file.
  // Shell and nav
  tofix_unchecked_aria: "To fix, not checked yet",
  tofix_failed_aria: "To fix, couldn't check",
  an_copied: "Copied",
  loc_line: "{file} line {line}",
  loc_file: "{file}",

  // Your setup map
  su_h1: "Your setup",
  su_sub: "What Claude Code loads when you start a session in {project}",
  su_switch: "Show where each comes from",
  su_card_h: "What shapes a session",
  su_card_q: "Pick a part to see its items and where each one is set",
  su_col_what: "Part",
  su_col_runs: "What applies",
  su_col_status: "Status",
  su_r_model_effort: "{model}, runs at {effort} effort",
  su_r_model_effort_model: "{model}",
  su_r_model_effort_effort: "Runs at {effort} effort",
  su_r_model_effort_none: "Not set, so defaults apply",
  su_r_agents_one: "{n} agent",
  su_r_agents_other: "{n} agents",
  su_r_agents_idle: "{n} with no runs in 30 days",
  su_r_instructions_one: "{n} file",
  su_r_instructions_other: "{n} files",
  su_r_instructions_lines_one: "{n} line",
  su_r_instructions_lines_other: "{n} lines",
  su_r_rules_one: "{n} file",
  su_r_rules_other: "{n} files",
  su_r_rules_on_demand_one: "{n} loads only for {globs}",
  su_r_rules_on_demand_other: "{n} load only for {globs}",
  su_r_skills_one: "{n} skill",
  su_r_skills_other: "{n} skills",
  su_r_hooks_one: "{n} hook",
  su_r_hooks_other: "{n} hooks",
  su_r_hooks_events_one: "on {n} event",
  su_r_hooks_events_other: "on {n} events",
  su_r_permissions_allow: "{n} allowed",
  su_r_permissions_deny: "{n} denied",
  su_r_permissions_ask_one: "{n} asks first",
  su_r_permissions_ask_other: "{n} ask first",
  su_r_permissions_mode: "Default mode {mode}",
  su_r_permissions_none: "No rules",
  su_r_mcp_one: "{n} server",
  su_r_mcp_other: "{n} servers",
  su_r_mcp_not_approved: "{n} not approved",
  su_r_plugins_one: "{n} plugin on",
  su_r_plugins_other: "{n} plugins on",
  su_r_plugins_off: "{n} off",
  su_r_output_style: "{active}",
  su_r_output_style_default: "Default",
  su_unread: "Couldn't read all its files",
  su_none_settings: "No settings found",
  su_none_agents: "No agents found",
  su_none_instructions: "No instruction files found",
  su_none_rules: "No rules files found",
  su_none_skills: "No skills found",
  su_none_hooks: "No hooks found",
  su_none_permissions: "No permission rules found",
  su_none_mcp: "No MCP servers found",
  su_none_plugins: "No plugins installed",
  su_nv_part: "Bar Tab can't see this part",
  su_unlisted:
    "{project} isn't on Bar Tab's project list, so Bar Tab doesn't read its project files. Only your user and managed setup shows here.",
  su_unlisted_link: "How a project gets on the list",
  // The version_gap notice above the map (M5 task 3b). Its link reuses dc_gap_link_*.
  su_n_version_gap:
    "You run Claude Code {installed}, but Bar Tab checked its rules on {checked_on}. If Claude Code changed how it decides, a status here may be wrong.",
  su_n_version_gap_some_one:
    "You run Claude Code {installed}. Bar Tab checked {due} rule on an older version, so a status that uses it may be wrong.",
  su_n_version_gap_some_other:
    "You run Claude Code {installed}. Bar Tab checked {due} rules on an older version, so a status that uses one may be wrong.",
  su_ld: "Loading your setup",

  // Scopes and scope cells
  sc_managed: "Managed",
  sc_managed_2: "Your organization",
  sc_command_line: "Command line",
  sc_command_line_2: "This launch only",
  sc_project_local: "Project local",
  sc_project_local_2: "Just you, this project",
  sc_project: "Shared project",
  sc_project_2: "Everyone in this project",
  sc_user: "User",
  sc_user_2: "You, every project",
  sc_plugin: "Plugin",
  sc_plugin_2: "From a plugin",
  sc_plugin_named: "Plugin {plugin}",
  sc_shell: "Your shell",
  sc_shell_2: "Seen at {time}, when Bar Tab started",
  ins_parent: "Parent folder",
  sc_none: "Nothing set here",
  su_nv: "Not visible here",
  su_nr: "Not read here",
  sc_unreadable: "Couldn't read",
  su_cell_settings_one: "{n} value",
  su_cell_settings_other: "{n} values",
  su_cell_agents_one: "{n} agent",
  su_cell_agents_other: "{n} agents",
  su_cell_instructions_one: "{n} file",
  su_cell_instructions_other: "{n} files",
  su_cell_rules_one: "{n} rule",
  su_cell_rules_other: "{n} rules",
  su_cell_skills_one: "{n} skill",
  su_cell_skills_other: "{n} skills",
  su_cell_hooks_one: "{n} hook",
  su_cell_hooks_other: "{n} hooks",
  su_cell_permissions_one: "{n} rule",
  su_cell_permissions_other: "{n} rules",
  su_cell_mcp_one: "{n} server",
  su_cell_mcp_other: "{n} servers",
  su_cell_plugins_one: "{n} plugin",
  su_cell_plugins_other: "{n} plugins",
  su_cell_output_style_one: "{n} style",
  su_cell_output_style_other: "{n} styles",
  su_cell_model_effort: "{model} at {effort}",
  su_cell_model: "{model}",
  su_cell_effort: "{effort} effort",

  // Parts, statuses, confidence
  sf_settings: "Settings",
  sf_agents: "Agents",
  sf_instructions: "Instructions",
  sf_rules: "Rules files",
  sf_skills: "Skills",
  sf_hooks: "Hooks",
  sf_permissions: "Permissions",
  sf_mcp: "MCP servers",
  sf_plugins: "Plugins",
  sf_output_style: "Output style",
  in_tested: "Tested",
  in_documented: "Documented",
  in_assumed: "Assumed",
  in_conf_tested: "Based on Claude Code's docs and tested on {version}.",
  in_conf_tested_nover: "Based on Claude Code's docs and tested.",
  in_conf_documented: "Based on Claude Code's docs, not tested yet.",
  in_conf_assumed: "Assumed, because Claude Code's docs don't cover this case.",
  in_conf_assumed_shell: "Assumed, because Bar Tab can't see the shell your session started in.",

  // Surface pages
  sp_sub_settings: "Every setting that shapes the main session in {project}",
  sp_sub_agents: "Agent files Claude Code finds for {project}",
  sp_sub_instructions: "Instruction files, in the order Claude Code loads them",
  sp_sub_rules: "Rules files and the files each one loads for",
  sp_sub_skills: "Skills Claude can use in {project}",
  sp_sub_hooks: "What runs at set points in a session",
  sp_sub_permissions: "Which tools Claude can use, and which need a yes first",
  sp_sub_mcp: "Servers that give Claude more tools",
  sp_sub_plugins: "Plugins turned on for {project}",
  sp_sub_output_style: "How Claude writes its replies",
  sp_g_model: "Model and effort",
  sp_g_other: "Other settings",
  sp_g_deny: "Deny",
  sp_g_ask: "Ask first",
  sp_g_allow: "Allow",
  sp_g_default_mode: "Default mode",
  sp_g_directory: "Extra folders",
  ag_g_ran: "Ran in the last 30 days",
  ag_g_no_runs: "No runs in the last 30 days",
  hk_ev_SessionStart: "When a session starts or resumes",
  hk_ev_Setup:
    "When Claude Code starts with --init-only, or with --init or --maintenance in -p mode",
  hk_ev_InstructionsLoaded: "When a CLAUDE.md or rules file loads",
  hk_ev_UserPromptSubmit: "When a prompt is sent, before Claude reads it",
  hk_ev_UserPromptExpansion: "When a command you type expands into a prompt",
  hk_ev_MessageDisplay: "While Claude's reply shows on screen",
  hk_ev_PreToolUse: "Before a tool call runs",
  hk_ev_PermissionRequest: "When a tool call needs a permission decision",
  hk_ev_PostToolUse: "After a tool call succeeds",
  hk_ev_PostToolUseFailure: "After a tool call fails",
  hk_ev_PostToolBatch: "After a batch of parallel tool calls finishes",
  hk_ev_PermissionDenied: "When auto mode denies a tool call",
  hk_ev_Notification: "When Claude Code sends a notification",
  hk_ev_SubagentStart: "When a subagent starts",
  hk_ev_SubagentStop: "When a subagent finishes",
  hk_ev_TaskCreated: "When a task is created",
  hk_ev_TaskCompleted: "When a task is marked complete",
  hk_ev_Stop: "When Claude finishes responding",
  hk_ev_StopFailure: "When a turn ends on an API error",
  hk_ev_TeammateIdle: "When a teammate on an agent team is about to go idle",
  hk_ev_ConfigChange: "When a configuration file changes during a session",
  hk_ev_CwdChanged: "When the working folder changes",
  hk_ev_DirectoryAdded: "When a working folder is added during a session",
  hk_ev_FileChanged: "When a watched file changes on disk",
  hk_ev_WorktreeCreate: "When a worktree is being created",
  hk_ev_WorktreeRemove: "When a worktree a hook created is being removed",
  hk_ev_PreCompact: "Before Claude Code compacts the context",
  hk_ev_PostCompact: "After Claude Code compacts the context",
  hk_ev_PreModelSwitch: "Before the model switches",
  hk_ev_PostModelSwitch: "After the session's model changes",
  hk_ev_SessionEnd: "When a session ends",
  hk_ev_Elicitation: "When an MCP server asks you for input",
  hk_ev_ElicitationResult: "After you answer an MCP server's request for input",
  hk_no_matcher: "Every time",
  sp_jump: "Jump to",
  sp_back: "Back to {part}",
  sp_gone_h: "This item isn't in {part} anymore",
  sp_gone_b: "It may have been renamed or removed since you opened it.",

  // Inspector, shared
  in_details_h: "Details",
  in_where_h: "Where it's set, top wins",
  in_why_h: "Why",
  in_copy: "Copy path",
  in_runs: "Runs with {value}",
  in_runs_model: "Runs on {value}",
  in_runs_effort: "Runs at {value}",
  in_origin_default: "Nothing sets it, so Claude Code's default applies.",
  in_origin_cap: "{item} lowers it.",
  in_origin_unknown: "Bar Tab can't tell what runs.",
  // Reviewed by tech-writer November 10. The sentence under an Overridden agent's headline, from
  // the check's by_file, by_via and by_layer params. The Lowered sentence is in_origin_cap above.
  in_origin_override_file: "{key} on line {line} of {file} wins.",
  in_origin_override_via: "{via} wins.",
  in_origin_override_layer: "{key} in {layer} wins.",
  in_set_value: "Set to {value} in {scope}, {where}.",
  in_set_at: "Set in {scope}, {where}.",
  in_set_plugin: "From the {plugin} plugin, {where}.",
  in_set_shell: "Set by {key} in your shell, as Bar Tab saw it at start.",
  in_nset_shell: "Not set when Bar Tab started",
  in_shell_note:
    "Bar Tab reads your shell's values once, when it starts. A terminal you open later can have different ones.",
  in_masked: "Bar Tab hides values that look like secrets.",
  in_masked_aria: "hidden value",
  in_link: "This file links to {path}.",
  in_may_change:
    "Bar Tab couldn't read a file that can set this, so the answer may change once it can.",
  ap_now: "Applies right away",
  ap_new_session: "Applies to new sessions",
  ap_restart: "Applies after you restart Claude Code",
  ap_reload_plugins: "Applies after plugins reload",
  in_usage_all: "In the last {days} days, all {total} main sessions ran on {value}.",
  in_usage_some: "In the last {days} days, {runs} of {total} main sessions ran on {value}.",
  in_usage_all_effort: "In the last {days} days, all {total} main sessions ran at {value}.",
  in_usage_some_effort: "In the last {days} days, {runs} of {total} main sessions ran at {value}.",
  in_usage_none: "No main sessions in the last {days} days.",
  sl_model: "Model",
  sl_effortLevel: "Effort",
  sl_maxEffortLevel: "Effort cap",
  sl_autoCompactWindow: "Compact window",
  sl_promptCacheTtl: "Cache lifetime",
  sl_alwaysThinkingEnabled: "Thinking",
  sl_fallbackModel: "Fallback models",
  sl_availableModels: "Allowed models",
  sl_modelSettings: "Per-model settings",
  sl_modelPricing: "Model prices",

  // Read-only box
  ro_h: "Can't change here",
  ro_managed: "Your organization manages this file, so Bar Tab can't change it.",
  ro_plugin:
    "This comes from the {plugin} plugin. Each update installs a fresh copy of its files, so Bar Tab leaves them as they are.",
  ro_plugin_2:
    "To change it, copy the file into your own agents folder and edit the copy. Your copy runs as its own agent, apart from the plugin's.",
  ro_claude_json_command:
    "Claude Code keeps user and local MCP servers in ~/.claude.json, which Bar Tab doesn't write. Use the claude mcp command in a terminal instead.",
  ro_command_line:
    "Flags such as --model last one launch and live in no file. Bar Tab can't see them, so it can't change them.",
  ro_not_visible: "Bar Tab can't see where this is set, so it can't change it.",
  ro_m6: "Editing comes in a later release. Nothing here is locked.",

  // Inspector, per kind
  ag_f_desc: "Description",
  ag_f_tools: "Tools",
  ag_f_color: "Color",
  ag_f_model: "Model",
  ag_f_effort: "Effort",
  ag_f_perm: "Permission mode",
  ag_f_hooks: "Hooks",
  ag_f_mcp: "MCP servers",
  ag_runs: "Runs on {model} at {effort}",
  ag_usage_one: "{n} run in the last {days} days",
  ag_usage_other: "{n} runs in the last {days} days",
  ag_usage_none: "No runs in the last {days} days",
  ag_runs_cost: "{runs} in {sessions}, {cost}, in the last {days} days",
  ag_sessions_one: "{n} session",
  ag_sessions_other: "{n} sessions",
  ag_ignored_h: "Fields Claude Code ignores here",
  ag_ignored_b:
    "Claude Code ignores these fields in a plugin's agents, so setting them has no effect.",
  ins_imports_h: "Imports, in load order",
  ins_imp_read: "Loaded",
  ins_imp_missing: "File not found",
  ins_imp_cycle: "Already in the chain",
  ins_imp_too_deep: "Past 4 hops",
  ins_imp_not_read: "Not read here. It's outside the folders Bar Tab reads.",
  ins_lines_one: "{n} line",
  ins_lines_other: "{n} lines",
  lo_always: "Loads at start",
  lo_on_demand: "Loads when Claude works with a matching file",
  lo_on_demand_folder: "Loads when Claude works in {folder}",
  lo_when_no_claude_md: "Loads only when no CLAUDE.md is found",
  ins_memory:
    "Auto memory isn't listed. Claude Code keeps it in its own folder, and Bar Tab doesn't read it.",
  ins_why:
    "Claude Code loads CLAUDE.md from this folder and every folder above it at start. It follows @ imports up to 4 hops deep.",
  ru_globs_h: "Loads for",
  ru_why:
    "A rules file with paths in its front matter loads only when Claude works with a file that matches. Without paths, it loads at start.",
  sk_runs: "Claude can use it when a task fits its description",
  sk_call: "Call it as",
  sk_legacy: "From a command file in .claude/commands",
  hk_f_event: "Event",
  hk_f_matcher: "Matches",
  hk_f_cmd: "Command",
  hk_f_type: "Does",
  hk_f_timeout: "Timeout",
  hk_ty_command: "Runs a command",
  hk_ty_http: "Sends an HTTP request",
  hk_ty_mcp_tool: "Calls an MCP tool",
  hk_ty_prompt: "Sends a prompt to Claude",
  hk_ty_agent: "Starts a subagent",
  hk_timeout_v: "{n} seconds",
  pm_f_tool: "Tool",
  pm_f_match: "Matches",
  pm_match_any: "Every use of {tool}",
  pm_f_mode: "Mode",
  pm_f_folder: "Folder",
  pm_runs_allow: "Allowed without asking",
  pm_runs_ask: "Asks you first",
  pm_runs_deny: "Blocked",
  pm_runs_mode: "Starts in {mode} mode",
  pm_runs_directory: "Claude can also work in this folder",
  pm_why:
    "Claude Code checks deny rules first, then ask, then allow, across every scope. The first match decides.",
  mc_f_transport: "Connects by",
  mc_f_cmd: "Command",
  mc_f_url: "URL",
  mc_f_args: "Arguments",
  mc_f_env: "Environment",
  mc_f_headers: "Headers",
  mc_f_approved: "Approved",
  mc_t_stdio: "A local command (stdio)",
  mc_t_http: "HTTP",
  mc_t_sse: "Server-sent events (SSE)",
  mc_t_ws: "WebSocket",
  mc_f_env_v_one: "{n} name, value hidden",
  mc_f_env_v_other: "{n} names, values hidden",
  mc_yes: "Yes",
  mc_no: "No",
  mc_runs_cmd: "Starts with {command}",
  mc_runs_url: "Connects to {url}",
  pl_runs: "Adds {list}",
  pl_runs_none: "Adds nothing Bar Tab can see",
  pl_contents_h: "What it adds",
  pl_f_version: "Version",
  pl_f_marketplace: "Marketplace",
  pl_f_enabled: "On in",
  pl_f_orphaned: "Old versions on disk",
  pl_on: "On",
  pl_off: "Off",
  pl_outside_runs: "Bar Tab can't tell what this plugin adds",
  pl_outside:
    "It's installed outside your Claude plugins folder, so Bar Tab doesn't read it. Anything it adds doesn't show here.",
  st_runs: "Claude writes in the {style} style",
  st_runs_default: "Claude writes in the default style",
  st_set: "Nothing sets an output style, so Claude Code uses its default.",
  st_builtin: "Built in",

  // Agents setup half and See why
  ag_q_picked: "Every agent in this project, including ones that didn't run",
  ag_open_setup: "Open in Your setup",
  ag_src_plugin: "Plugin {plugin}",
  ag_src_managed: "Managed",
  ag_chk_unchecked: "Not checked",
  ag_chk_unchecked_aria:
    "Not checked, because Model check doesn't cover plugin or managed agents. Their setup shows in Your setup.",
  mc_see_why: "See why",
  mc_see_why_aria: "See why for {agent}",

  // To fix page
  fx_h1: "To fix",
  fx_sub_one: "{n} problem to fix in {project}",
  fx_sub_other: "{n} problems to fix in {project}",
  fx_sub_none: "Nothing to fix in {project}",
  fx_g_couldnt_read: "Couldn't read",
  fx_g_wont_load: "Won't load",
  fx_g_not_as_set: "Not as set",
  fx_g_cant_tell: "Can't tell",
  fx_g_notice: "Notices",
  fx_g_aria: "{group}, {n}",
  fx_q_couldnt_read: "Files Bar Tab couldn't open",
  fx_q_wont_load: "Claude Code skips these",
  fx_q_not_as_set: "These run differently than they're set",
  fx_q_cant_tell: "Not counted, because Bar Tab can't tell what applies",
  fx_q_notice: "Not counted, because they aren't problems in your setup",
  fx_open: "Open {item}",
  fx_copy_path_aria: "Copy path of {file}",
  fx_copy_cmd_aria: "Copy command for {thing}",
  fx_cmd_note:
    "Bar Tab only copies this command and never runs it. Paste it in a terminal to remove the server.",
  fx_cant_managed: "Can't fix here. Your organization manages this file.",
  fx_cant_plugin:
    "Can't fix here. It comes from a plugin, and the next update would undo a change.",
  fx_cant_not_visible: "Can't fix here. Bar Tab can't see where this is set.",
  fx_cant_not_fixable: "Nothing to fix here.",
  fx_cant_walk_stopped: "Can't fix here. It's a limit of how far Bar Tab looks.",
  fx_empty_h: "Nothing to fix",
  fx_empty: "Everything Bar Tab can check loads and runs as set. New problems show up here.",
  fx_empty_a: "Open Your setup",
  fx_ld: "Checking {project} for problems",
  fx_err_h: "Couldn't check {project} for problems",

  // Problem codes. _t is the title, _c the cause and _q the consequence.
  pc_permission_t: "Bar Tab can't open {thing}",
  pc_not_utf8_t: "Bar Tab can't read {thing}",
  pc_too_large_t: "{thing} is too large for Bar Tab to read",
  pc_folder_unlistable_t: "Bar Tab can't list the {thing} folder",
  pc_vanished_t: "{thing} disappeared while Bar Tab read it",
  pc_transcript_unreadable_t: "Bar Tab can't read the transcript {thing}",
  pc_transcript_unreadable_c:
    "Bar Tab couldn't open {file} when it read this project's transcripts.",
  pc_transcript_unreadable_q: "Its session is missing from Review and Live.",
  pc_read_q: "Any problems in this file stay hidden until Bar Tab can read it.",
  pc_folder_unlistable_q: "Anything in this folder stays hidden until Bar Tab can list it.",
  pc_vanished_q: "If it was moved or removed on purpose, there's nothing to fix.",
  pc_json_invalid_t: "{thing} isn't valid JSON",
  pc_json_invalid_c: "{where} has a JSON syntax error.",
  pc_json_invalid_q: "Claude Code can't use what this file sets until the error is fixed.",
  pc_not_object_t: "{thing} doesn't hold a JSON object",
  pc_not_object_c: "The top level of {file} isn't a JSON object, so nothing in it can be read.",
  pc_not_object_q: "Claude Code can't use what this file sets.",
  pc_not_object_c_key: "In {file}, {key} isn't a JSON object.",
  pc_managed_invalid_t: "Managed settings can't be read",
  pc_managed_invalid_c: "{where} isn't valid JSON, or its top level isn't an object.",
  pc_managed_invalid_q: "Claude Code may not apply your organization's settings as intended.",
  pc_value_invalid_t: "{thing} has a value Claude Code rejects",
  pc_value_invalid_c: "{where} sets {key} to {value}, which Claude Code doesn't accept.",
  pc_value_invalid_q: "Claude Code drops this value, so it doesn't apply.",
  pc_frontmatter_invalid_t: "{thing} has front matter Claude Code can't read",
  pc_frontmatter_invalid_c: "{where} starts front matter that isn't valid YAML.",
  pc_frontmatter_invalid_q: "Claude Code can't read the settings in it.",
  pc_agent_no_name_t: "{thing} has no name",
  pc_agent_no_name_c: "{where} starts front matter with no name.",
  pc_agent_no_name_q: "Claude Code skips this agent.",
  pc_agent_no_description_t: "{thing} has no description",
  pc_agent_no_description_c: "{where} starts front matter with no description.",
  pc_agent_no_description_q: "Claude Code skips this agent.",
  pc_agent_not_md_t: "{thing} isn't a Markdown file",
  pc_agent_not_md_c: "{file} is in an agents folder, but Claude Code reads only .md files there.",
  pc_agent_not_md_q: "Claude Code skips it.",
  pc_same_name_in_folder_t: "{thing} is defined twice in one folder",
  pc_same_name_in_folder_c: "{file} and {other_file} use the same name.",
  pc_same_name_in_folder_q: "Claude Code loads only one of them.",
  pc_same_name_in_folder_c_nofile: "Another file in this folder uses the same name.",
  pc_skill_no_md_t: "Skill folder {thing} has no SKILL.md",
  pc_skill_no_md_c: "{folder} has no SKILL.md file in it.",
  pc_skill_no_md_q: "Claude Code doesn't load it as a skill.",
  pc_import_missing_t: "An import in {thing} points to a missing file",
  pc_import_missing_c: "{where} imports {target}, which doesn't exist.",
  pc_import_missing_q: "Claude Code skips that import.",
  pc_import_too_deep_t: "An import in {thing} is more than 4 hops deep",
  pc_import_too_deep_c: "{where} imports {target}, past the 4 hops Claude Code follows.",
  pc_import_too_deep_q: "Claude Code doesn't load it.",
  pc_import_cycle_t: "Imports in {thing} loop back",
  pc_import_cycle_c: "{where} imports {target}, which is already in the chain.",
  pc_import_cycle_q: "That import doesn't load a second time.",
  pc_hook_bad_event_t: "Hook event {event} doesn't exist",
  pc_hook_bad_event_c: "{where} names {event}, which isn't a Claude Code hook event.",
  pc_hook_bad_event_q: "Claude Code skips these hooks.",
  pc_hook_bad_handler_t: "A {event} hook can't run",
  pc_hook_bad_handler_t_noevent: "A hook can't run",
  pc_hook_bad_handler_q: "Claude Code skips this hook.",
  pc_hook_why_not_object: "{where} has a hook entry that isn't a JSON object.",
  pc_hook_why_no_type: "{where} has a hook with no type.",
  pc_hook_why_unknown_type: "{where} has a hook type Claude Code doesn't know.",
  pc_hook_why_no_command: "{where} has a command hook with no command.",
  pc_hook_why_bad_args: "{where} has a command hook whose args aren't a list of plain values.",
  pc_hook_why_no_url: "{where} has an HTTP hook with no URL.",
  pc_hook_why_no_tool: "{where} has an MCP tool hook without both a server and a tool.",
  pc_hook_why_no_prompt: "{where} has a prompt or agent hook with no prompt.",
  pc_mcp_bad_entry_t: "MCP server {thing} won't load",
  pc_mcp_bad_entry_q: "Claude Code skips this server, so its tools aren't available.",
  pc_mcp_why_no_command_or_url:
    "In {file}, the {name} entry under mcpServers sets neither a command nor a URL.",
  pc_mcp_why_url_without_type:
    "{where} gives {name} a URL but no type, which Claude Code doesn't accept.",
  pc_mcp_why_no_url: "{where} gives {name} a remote type but no URL.",
  pc_mcp_why_no_command: "{where} gives {name} no command.",
  pc_mcp_why_unknown_type: "{where} gives {name} a type Claude Code doesn't know.",
  pc_mcp_why_bad_type: "{where} gives {name} a type that isn't text.",
  pc_mcp_why_bad_field: "{where} has a field in {name} with the wrong kind of value.",
  pc_mcp_why_not_object: "{where} has an entry for {name} that isn't a JSON object.",
  pc_plugin_not_installed_t: "Plugin {thing} isn't installed",
  pc_plugin_not_installed_c:
    "{where} turns it on, but Bar Tab can't find it in your installed plugins.",
  pc_plugin_not_installed_q: "Claude Code can't load what it would add.",
  pc_plugin_manifest_invalid_t: "Plugin {thing} has a broken plugin.json",
  pc_plugin_manifest_invalid_c: "{where} isn't valid JSON or has no name.",
  pc_plugin_manifest_invalid_q: "Claude Code can't load this plugin.",
  pc_output_style_missing_t: "Output style {style} doesn't exist",
  pc_output_style_missing_c: "{where} picks {style}, and Bar Tab can't find a style by that name.",
  pc_output_style_missing_q: "Claude Code falls back to the default style.",
  pc_permission_rule_invalid_t: "A permission rule isn't valid",
  pc_permission_rule_invalid_c:
    "{where} has the rule {rule} under {kind}, and Claude Code can't parse it.",
  pc_permission_rule_invalid_q: "Claude Code skips this rule and keeps the rest.",
  pc_ignored_t: "{thing} is set where Claude Code doesn't read it",
  pc_ignored_c: "{where} sets {key} to {value}, but Claude Code doesn't read it there.",
  pc_ignored_q: "Changing it there has no effect.",
  pc_ignored_c_paths: "{where} has front matter Claude Code can't read, so it ignores paths.",
  pc_ignored_q_paths: "This rule loads at start, not only for matching files.",
  pc_lowered_t: "{thing} runs lower than it's set",
  pc_lowered_c: "{where} sets {key} to {value}, and a cap lowers it.",
  pc_lowered_q: "It runs at a lower value than you set.",
  // Reviewed by tech-writer November 10. The To fix row of an agent a cap lowers. {cap} is the
  // cap's name ("Effort cap"), {value} what the file sets and {runs} what runs.
  pc_agent_lowered_t: "{thing} runs lower than its file sets",
  pc_agent_lowered_c: "{where} sets {setting} to {value}. {cap} lowers it to {runs}.",
  pc_agent_lowered_q: "Its {setting} is {runs}, not {value}.",
  pc_plugin_field_ignored_t: "{thing} sets a field Claude Code ignores in plugin agents",
  pc_plugin_field_ignored_c: "{where} sets {field}, which plugin agents can't use.",
  pc_plugin_field_ignored_q: "{thing} runs without it.",
  pc_hooks_disabled_t: "Hooks are turned off",
  pc_hooks_disabled_c: "{where} sets {flag}.",
  pc_hooks_disabled_q_all_one: "Your {n} hook doesn't run.",
  pc_hooks_disabled_q_all_other: "None of your {n} hooks run.",
  pc_hooks_disabled_q_managed_one:
    "Only hooks your organization allows run, so {n} of yours doesn't.",
  pc_hooks_disabled_q_managed_other:
    "Only hooks your organization allows run, so {n} of yours don't.",
  pc_unknown_t: "{thing} is unknown",
  pc_unknown_c: "{where} sets {key}, but something Bar Tab can't see may change it.",
  pc_unknown_q: "Bar Tab can't show which value runs.",
  pc_unknown_c_nofile: "Nothing Bar Tab reads sets it, and something it can't see decides.",
  pc_import_out_of_scope_t: "An import in {thing} isn't read",
  pc_import_out_of_scope_c: "{where} imports {target}, which is outside the folders Bar Tab reads.",
  pc_import_out_of_scope_q: "Bar Tab can't tell what it adds.",
  pc_env_not_visible_t: "Bar Tab can't tell where {thing} connects",
  pc_env_not_visible_c:
    "{where} uses {vars} with no default, and Bar Tab can't see the environment your session starts in.",
  pc_env_not_visible_q: "Bar Tab can't check this server.",
  pc_plugin_format_unknown_t: "Bar Tab doesn't know the format of {thing}",
  pc_plugin_format_unknown_c: "{file} has a shape Bar Tab doesn't know.",
  pc_plugin_format_unknown_q: "Plugins it lists may be missing from Your setup.",
  pc_walk_stopped_t: "Bar Tab stopped looking for nested files",
  pc_walk_stopped_c:
    "This project has more folders than Bar Tab looks through for nested CLAUDE.md files and skills.",
  pc_walk_stopped_q: "Some nested files may be missing from Your setup.",
  pc_frontmatter_reader_gap_t: "Bar Tab can't fully read {thing}'s front matter",
  pc_frontmatter_reader_gap_c:
    "{where} uses YAML that Bar Tab's agent check doesn't read, though Claude Code may.",
  pc_frontmatter_reader_gap_q: "Bar Tab can't check its model and effort.",
  pc_plugin_outside_plugins_t: "Bar Tab doesn't read the {thing} plugin",
  pc_plugin_outside_plugins_c: "It's installed at {file}, outside your Claude plugins folder.",
  pc_plugin_outside_plugins_q: "What it adds doesn't show in Your setup.",
  pc_rows_no_usage_one:
    "{n} transcript file has requests with no usage data, so those requests aren't counted.",
  pc_rows_no_usage_other:
    "{n} transcript files have requests with no usage data, so those requests aren't counted.",

  // Reason codes, the inspector Why line (ItemReason.code), and the causes behind Couldn't read
  rs_in_effect: "This is the value that applies.",
  rs_overridden: "Another setting wins over this one.",
  rs_ignored: "Claude Code doesn't use it here, so it has no effect.",
  rs_ignored_excluded: "{setting} skips this file with the pattern {pattern}.",
  rs_lowered: "A cap lowers it.",
  rs_invalid: "Claude Code doesn't accept this value.",
  rs_default: "Claude Code's default applies, because nothing sets it or it's set to the default.",
  rs_unknown: "Bar Tab can't tell which value applies.",
  rs_agent_loads: "Claude Code loads this agent from {file}.",
  rs_agent_overrides:
    "Claude Code uses {file}. An agent with the same name in {other_file} doesn't load.",
  rs_agent_overrides_noother:
    "Claude Code uses {file}. A lower scope has an agent with the same name.",
  rs_agent_no_description: "Its front matter has no description, so Claude Code skips it.",
  rs_same_name_in_folder:
    "{other_file} in the same folder uses the same name. Claude Code loads only one of them.",
  rs_same_name_in_folder_noother:
    "Another file in this folder uses the same name. Claude Code loads only one of them.",
  rs_frontmatter_invalid: "The front matter at the top of this file isn't valid YAML.",
  rs_frontmatter_reader_gap:
    "Bar Tab's agent check can't read this front matter, so it can't confirm the model and effort.",
  rs_hooks_disabled: "{flag} turns hooks off, so this one doesn't run.",
  rs_mcp_bad_entry: "Its entry in {file} is broken, so Claude Code skips it.",
  rs_mcp_not_approved: "Claude Code skips this server until you approve it.",
  rs_mcp_not_approved_by: "{by} turns this server off.",
  rs_env_not_visible:
    "Variables with no default depend on the environment your session starts in, which Bar Tab can't see.",
  rs_plugin_loads: "It's on, and Claude Code loads what it adds.",
  rs_plugin_not_enabled: "It's installed, but no settings file turns it on.",
  rs_plugin_not_installed: "A settings file turns it on, but it isn't installed.",
  rs_plugin_manifest_invalid:
    "Its plugin.json is broken or has no name, so Claude Code can't load it.",
  rs_plugin_outside_plugins:
    "It's installed outside your Claude plugins folder, so Bar Tab doesn't read it. Anything it adds doesn't show here.",
  rs_agent_source_unchecked:
    "Not checked, because Model check doesn't cover plugin or managed agents. Their setup shows in Your setup.",
  cr_r_permission: "File permissions block reading {file}.",
  cr_r_not_utf8: "{file} isn't valid UTF-8 text.",
  cr_r_too_large: "{file} is over 1 MB, the most Bar Tab reads.",
  cr_r_vanished: "{file} was removed while Bar Tab read it.",
  cr_r_folder_unlistable: "File permissions block listing {file}.",

  // Empty, loading and errors
  cr_b: "The list below has only what Bar Tab could read.",
  cr_fix: "Once Bar Tab can open the file, it reads it on its next refresh.",
  em_settings:
    "No settings found for this project. A setting you add to a settings file shows up here.",
  em_agents:
    "No agents found. An agent file you add to .claude/agents here, or to your user agents folder, shows up in this list.",
  em_instructions:
    "No instruction files found. A CLAUDE.md you add to this project, or to your user folder, shows up in this list.",
  em_rules:
    "No rules files found. A file you add to .claude/rules here, or to your user rules folder, shows up in this list.",
  em_skills:
    "No skills found in this project. A skill you add to .claude/skills here, or to your user skills folder, shows up in this list.",
  em_hooks:
    "No hooks found. A hook you add to a settings file, an agent or a plugin shows up in this list.",
  em_permissions:
    "No permission rules found. A rule you add to a settings file shows up in this list.",
  em_mcp:
    "No MCP servers found. A server you add with claude mcp add, or in .mcp.json, shows up in this list.",
  em_plugins: "No plugins installed. A plugin you install shows up in this list.",
  em_a_copy_folder: "Copy folder path",
  em_a_copy_file: "Copy file path",
  em_a_docs: "Open the docs",
  em_nv: "Bar Tab can't see where this part is set, so it can't list anything here.",

  // Task 15, Your setup and the surface pages. Reviewed by tech-writer November 10.
  bc_label: "Breadcrumb",
  in_line: "line {n}",
  in_masked_word: "Hidden",
  in_lock_word: "Read only",

  // Task 16, Agents inspector usage for any Review range. Reviewed by tech-writer November 10.
  ag_runs_n_one: "{n} run",
  ag_runs_n_other: "{n} runs",
  ag_runs_cost_range: "{runs} in {sessions}, {cost}, {range}",
  ag_usage_none_range: "No runs {range}",

  // Task 20 part B, words for the board's hook and per-model lines. Reviewed by tech-writer
  // November 10. hk_nm_PreToolUse keeps the board's "Before {tool}" (tech-writer suggested
  // "Before {tool} runs" and accepts this form).
  hk_nm_PreToolUse: "Before {tool}",
  hk_nm_PostToolUse: "After {tool} succeeds",
  hk_nm_PostToolUseFailure: "After {tool} fails",
  hk_wh_PreToolUse: "before each {tool} call",
  hk_wh_PostToolUse: "after each {tool} call that succeeds",
  hk_wh_PostToolUseFailure: "after each {tool} call that fails",
  hk_runs: "{does} {when}",
  hk_or: "{list} or {last}",
  sl_ms_entry: "{model} ({fields})",
  sl_ms_field: "{label} {value}",

  // Help popovers (M5). Draft labels from the designer, final words from the task 2 deck.
  hp_trigger: "About {title}",
  hp_numbers: "What each one means",
  hp_reading: "How to read it",
  hp_list_status: "The status words",
  hp_list_scopes: "The scopes",
  hp_list_confidence: "The confidence words",
  hp_list_project_state: "The project states",
  hp_this_column: "This column",
  hp_this_setting: "Shown here",
  hp_glossary_link: "{term} in the glossary",
  hp_close: "Close",
  // Meanings for the shared lists (lists.ts), from the task 2 deck
  cf_tested: "Checked by a test on the Claude Code version the rule names.",
  cf_documented: "Claude Code's docs say so, and the rule links the page.",
  cf_assumed:
    "Neither the docs nor a test backs the whole rule yet, so read it as a careful guess.",
  sc_shell_def: "Environment variables, read once when Bar Tab started",
  pk_state_ok_d:
    "The folder and its .claude folder are both there, so it opens with its usage and its full setup.",

  // How Claude Code decides (M5). Group names per rules.json key (a dot becomes an underscore),
  // then one sentence per rule, keyed rl_<rule_id> (tech-writer, November 10).
  rg_model: "Model",
  rg_effortLevel: "Effort level",
  rg_effort: "Agent effort",
  rg_modelSettings: "Effort per model",
  rg_maxEffortLevel: "Effort cap",
  rg_modelSettings_maxEffortLevel: "Effort cap per model",
  rg_autoCompactWindow: "Auto-compact window",
  rg_modelSettings_autoCompactWindow: "Auto-compact window per model",
  rg_promptCacheTtl: "Cache lifetime",
  rg_subagentPromptCacheTtl: "Agent cache lifetime",
  rg_alwaysThinkingEnabled: "Extended thinking",
  rg_fallbackModel: "Fallback models",
  rg_availableModels: "Available models",
  rg_agentFile: "Agent files",
  rg_settingsFile: "Settings files",
  rg_env: "Settings env block",
  rg_rulesFile: "Rules files",
  "rl_effort-level-user-settings-opus-5-5":
    "Opus 5.5 and later models ignore a top-level effortLevel in user settings and take that file's level only from modelSettings.",
  "rl_model-main-session-order":
    "--model beats ANTHROPIC_MODEL, which beats the model key in any settings file, managed settings included.",
  "rl_model-main-default":
    "With no model set, the session starts on Claude Code's default, which depends on your account type, so Bar Tab can't name it.",
  "rl_env-block-order":
    "An env block in settings overwrites the same variable from your shell, and the highest settings file that sets it wins.",
  "rl_effort-level-layer-order":
    "CLAUDE_CODE_EFFORT_LEVEL beats --effort, which beats every settings file, and the highest file with a level that counts for the model wins.",
  "rl_model-settings-effort-per-model":
    "Each model's effort comes from the highest settings file that sets a level for it, in modelSettings or a top-level effortLevel that applies.",
  "rl_max-effort-level-lowest-cap":
    "When several files set maxEffortLevel, the lowest cap applies, so no file can raise a cap set in another.",
  "rl_max-effort-level-replaced-in-file":
    "A modelSettings cap replaces the top-level maxEffortLevel for that one model, but only within the settings source that sets both.",
  "rl_max-effort-level-default":
    "With no maxEffortLevel in any settings file, Bar Tab sees no cap, but a Claude Enterprise admin can cap effort per role.",
  "rl_prompt-cache-ttl-order":
    "CLAUDE_CODE_PROMPT_CACHE_TTL beats promptCacheTtl in any settings file, the highest file wins, and only 5m or 1h counts.",
  "rl_subagent-prompt-cache-ttl-order":
    "CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL beats subagentPromptCacheTtl in settings, which beats an agent's experimental.cacheTtl, and only 5m or 1h counts.",
  "rl_auto-compact-window-order":
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW beats --autocompact, which beats autoCompactWindow in settings, and the highest file wins.",
  "rl_subagent-model-order":
    "An agent's model in its frontmatter, inherit included, beats CLAUDE_CODE_SUBAGENT_MODEL, which beats the main session's model.",
  "rl_subagent-model-force":
    "With CLAUDE_CODE_SUBAGENT_MODEL_FORCE on, agents run on CLAUDE_CODE_SUBAGENT_MODEL and Claude Code ignores the frontmatter model.",
  "rl_subagent-model-force-alone":
    "With only CLAUDE_CODE_SUBAGENT_MODEL_FORCE on, agents run on the main session's model and Claude Code ignores the frontmatter model.",
  "rl_subagent-model-default":
    "With no model set for an agent, it runs on the main session's model, so Bar Tab can name it only when it knows that model.",
  "rl_effort-env-auto-sends-none":
    "Setting CLAUDE_CODE_EFFORT_LEVEL to auto or unset sends no effort level, so the API's default for the model applies.",
  "rl_effort-level-user-settings-model-unknown":
    "When Bar Tab doesn't know the session's model, it can't say whether a top-level effortLevel in user settings counts.",
  "rl_effort-env-empty-ignored":
    "An empty CLAUDE_CODE_EFFORT_LEVEL counts as not set, so the next source decides the effort.",
  "rl_agent-effort-env-empty-ignored":
    "An empty CLAUDE_CODE_EFFORT_LEVEL counts as not set, so the next source decides an agent's effort.",
  "rl_effort-default-model-unknown":
    "When no effort level counts and Bar Tab doesn't know the session's model, it can't name the default level.",
  "rl_effort-default-no-effort-support":
    "Haiku 4.5 doesn't support effort, so Claude Code sends no level and there's no default to show.",
  "rl_effort-default-by-model":
    "When no effort level counts, the session runs at the model's own default level.",
  "rl_effort-level-settings-values":
    "Settings files take low, medium, high or xhigh for effortLevel, so Claude Code skips any other value, max included.",
  "rl_model-settings-effort-values":
    "A modelSettings effort entry takes low, medium, high or xhigh, and Claude Code skips any other value for that model.",
  "rl_effort-flag-values":
    "--effort takes low, medium, high, xhigh or max, and Claude Code warns and ignores any other level.",
  "rl_effort-lowered-by-cap":
    "When maxEffortLevel is set, a higher effort runs at the cap, whether it comes from a variable, a flag, a file or the default.",
  "rl_effort-lowered-by-cap-model-unknown":
    "When Bar Tab doesn't know the model, it applies the top-level maxEffortLevel cap, though a modelSettings cap could change it.",
  "rl_effort-lowered-unsupported-level":
    "A level the model lacks runs at the highest level it has below that, so xhigh runs as high on Opus 4.6.",
  "rl_effort-ignored-no-effort-support":
    "Haiku 4.5 doesn't support effort, so any effort level set for it has no effect.",
  "rl_agent-effort-order":
    "CLAUDE_CODE_EFFORT_LEVEL beats an agent's effort frontmatter, which beats --effort and the settings that count for the agent's model.",
  "rl_agent-effort-lowered-by-cap":
    "When maxEffortLevel caps an agent's model, a higher effort for that agent runs at the cap.",
  "rl_agent-effort-lowered-by-cap-model-unknown":
    "When Bar Tab can't tell an agent's model, it applies the top-level maxEffortLevel cap, though a modelSettings cap could change it.",
  "rl_agent-effort-lowered-unsupported-level":
    "When an agent's model lacks the level set, the agent runs at the highest level the model has below it.",
  "rl_agent-effort-user-settings-opus-5-5":
    "An agent on Opus 5.5 or later ignores a top-level effortLevel in user settings and takes a level only from modelSettings.",
  "rl_agent-effort-user-settings-model-unknown":
    "When Bar Tab can't tell an agent's model, it can't say whether a top-level effortLevel in user settings counts for it.",
  "rl_agent-effort-default-model-unknown":
    "When no effort level counts for an agent and Bar Tab can't tell its model, it can't name the default level.",
  "rl_agent-effort-default-no-effort-support":
    "An agent on Haiku 4.5 gets no effort level, because that model doesn't support effort.",
  "rl_agent-effort-default-by-model":
    "When no effort level counts for an agent's model, the agent runs at that model's default level.",
  "rl_model-settings-name-matching":
    "A modelSettings entry matches its model by canonical name, alias, date suffix, [1m] or a provider ID, and within one file a canonical-name entry beats an alias entry.",
  "rl_model-settings-max-effort-per-model":
    "A modelSettings cap replaces that file's top-level maxEffortLevel for one model, and across files the lowest cap still applies.",
  "rl_max-effort-level-values":
    "maxEffortLevel takes low, medium, high, xhigh or max, where max sets no cap, and Claude Code skips any other value.",
  "rl_model-settings-max-effort-values":
    "A modelSettings cap takes low, medium, high, xhigh or max, and Claude Code skips any other value for that model.",
  "rl_model-settings-auto-compact-window":
    "A per-model autoCompactWindow beats the top-level one in the same file, but across files the highest file still wins.",
  "rl_prompt-cache-force-5m":
    "FORCE_PROMPT_CACHING_5M forces a five-minute cache for the main conversation, whatever any other variable or settings file sets.",
  "rl_subagent-prompt-cache-force-5m":
    "FORCE_PROMPT_CACHING_5M forces a five-minute cache for agents too, whatever their settings or frontmatter say.",
  "rl_prompt-cache-enable-1h":
    "ENABLE_PROMPT_CACHING_1H asks for a one-hour cache for the main conversation when no other variable or settings file sets one.",
  "rl_subagent-prompt-cache-enable-1h":
    "ENABLE_PROMPT_CACHING_1H asks for a one-hour cache for agents when no other variable, settings file or experimental.cacheTtl sets one.",
  "rl_prompt-cache-default-by-plan":
    "With nothing setting it, your plan decides the main conversation's cache lifetime, one hour on a subscription within plan usage and five minutes otherwise.",
  "rl_subagent-prompt-cache-default":
    "With nothing setting it, an agent's cache lasts five minutes on every plan, subscriptions included.",
  "rl_auto-compact-window-empty":
    "Claude Code ignores an empty CLAUDE_CODE_AUTO_COMPACT_WINDOW, so the next source sets the auto-compact window.",
  "rl_auto-compact-window-values":
    "Claude Code moves a CLAUDE_CODE_AUTO_COMPACT_WINDOW value into the 100000 to 1000000 range and ignores a settings value below 100000.",
  "rl_auto-compact-window-default":
    "With nothing setting it, Claude Code uses the window tuned for the model, 1000000 tokens on Opus 5.5.",
  "rl_agent-auto-compact-window":
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW beats an agent's frontmatter, and otherwise the frontmatter can only lower the window the session would use.",
  "rl_agent-auto-compact-window-values":
    "An agent's frontmatter window takes 100000 to 1000000 as a plain number, and Claude Code ignores anything else, 200k included.",
  "rl_agent-auto-compact-window-default":
    "With nothing setting a window, an agent inherits the one tuned for the session's model, which its frontmatter can only lower.",
  "rl_agent-file-location-order":
    "When agents share a name, Claude Code uses the one from the highest place, from managed settings down to a plugin.",
  "rl_agent-file-project-over-user":
    "When a project agent and a user agent share a name, the project agent wins.",
  "rl_agent-file-nested-closest":
    "When nested .claude/agents folders define the same name, the one closest to the working directory wins.",
  "rl_agent-file-same-name-one-tree":
    "When two files in one agents folder share a name, Claude Code loads only one, in filesystem read order.",
  "rl_agent-file-reader-rejected":
    "Some agent files load in Claude Code even though Bar Tab can't read their frontmatter safely, so their values stay unknown.",
  "rl_agent-file-reader-rejected-untested":
    "When Bar Tab rejects frontmatter in a form nobody has tested, it can't say whether Claude Code loads the file.",
  "rl_agent-file-skipped":
    "Claude Code loads only .md agent files with a name and a description, and skips one whose frontmatter it can't parse.",
  "rl_agent-file-unknown-field":
    "Claude Code ignores a frontmatter field it doesn't recognize, and the agent still loads.",
  "rl_settings-file-unreadable":
    "When Bar Tab can't read a managed settings file, it can't see its values, and Claude Code may start without that policy too.",
  "rl_settings-file-unreadable-untested":
    "When Bar Tab can't read a user, project or local settings file, it can't tell whether Claude Code reads it.",
  "rl_settings-file-managed-unparsed":
    "Claude Code refuses to start while a managed settings file isn't a valid JSON object.",
  "rl_settings-file-unparsed-skipped":
    "Claude Code skips a whole user, project or local settings file that isn't a valid JSON object.",
  "rl_rules-files-listed":
    "Claude Code loads every .md file in the user and project rules folders, user rules first, and neither set overrides the other.",
  "rl_always-thinking-no-effect":
    "Fable 5 and later models always think, so alwaysThinkingEnabled false and MAX_THINKING_TOKENS=0 have no effect on them.",
  "rl_always-thinking-model-unknown":
    "When Bar Tab doesn't know the session's model, it can't say whether a setting that turns thinking off works.",
  "rl_always-thinking-value-wrong":
    "When alwaysThinkingEnabled isn't true or false, or MAX_THINKING_TOKENS isn't a whole number, Bar Tab can't say what happens.",
  "rl_always-thinking-order":
    "MAX_THINKING_TOKENS beats alwaysThinkingEnabled for one session, and among settings files the highest one wins.",
  "rl_always-thinking-default-always-on":
    "Fable 5 and later models always think, so nothing can turn thinking off for them.",
  "rl_always-thinking-default":
    "With nothing setting it, extended thinking is on for every model that supports it.",
  "rl_fallback-model-chain-limits":
    "Claude Code removes duplicates from a fallback chain, drops models outside the allowed list and keeps at most three.",
  "rl_fallback-model-chain-unclear":
    "Bar Tab can't always tell which models stay in a fallback chain, such as when an entry is default or a provider ID.",
  "rl_fallback-model-value-wrong":
    "When fallbackModel isn't a list of model names, Bar Tab can't say what Claude Code does with it.",
  "rl_fallback-model-order":
    "--fallback-model beats every settings file, and Claude Code takes the whole chain from the highest file, with no merging.",
  "rl_fallback-model-default":
    "With no fallback chain set, a failed request isn't retried on another model.",
  "rl_available-models-managed-empty":
    "An empty availableModels list in managed settings blocks every named model selection.",
  "rl_available-models-value-wrong":
    "When availableModels isn't a list of model names, Bar Tab can't say what Claude Code does with it.",
  "rl_available-models-order":
    "A managed availableModels list applies as it is, and without one Claude Code combines the lists from your other files.",
  "rl_available-models-default":
    "With no availableModels list in any settings file, every model is available.",

  // How Claude Code decides (M5 task 3b). Direction C, a settings list and a page per setting.
  dc_sub: "The rules Bar Tab uses to work out which value Claude Code runs with",
  dc_gap_all_one:
    "You run Claude Code {installed}, but Bar Tab checked its {due} rule on {checked_on}. If Claude Code changed how it decides, the rule may be out of date.",
  dc_gap_all_other:
    "You run Claude Code {installed}, but Bar Tab checked all {due} rules on {checked_on}. If Claude Code changed how it decides, some may be out of date.",
  dc_gap_some_one:
    "You run Claude Code {installed}. Bar Tab checked {due} rule on an older version, so it may be out of date.",
  dc_gap_some_other:
    "You run Claude Code {installed}. Bar Tab checked {due} rules on an older version, so they may be out of date.",
  dc_gap_link_one: "Show the rule to re-check",
  dc_gap_link_other: "Show the {n} rules to re-check",
  dc_search_label: "Search rules",
  dc_search_ph: "A setting, a rule id or any word",
  // The SearchField clear button and the no-results button, on both Reference pages
  sf_clear: "Clear search",
  dc_conf_label: "Confidence",
  dc_conf_all: "All",
  dc_count_one: "{n} rule",
  dc_count_other: "{n} rules",
  dc_count_of: "{n} of {total} rules",
  dc_count_ann_one: "{n} rule shown",
  dc_count_ann_other: "{n} rules shown",
  dc_count_ann_of: "{n} of {total} rules shown",
  dc_count_ann_none: "No rules match",
  dc_loading: "Loading rules",
  dc_list_of: "{n} of {total}",
  dc_results_one: "{n} rule in {g} setting",
  dc_results_other_one_setting: "{n} rules in {g} setting",
  dc_results_other: "{n} rules in {g} settings",
  dc_set_sub_one: "{n} rule. Applies to {scopes}.",
  dc_set_sub_other: "{n} rules. Applies to {scopes}.",
  dc_scope_main: "the main session",
  dc_scope_agent: "agents",
  dc_scope_model: "each model",
  dc_order_h: "Where Claude Code looks, top wins",
  dc_q_invalid: "When Claude Code won't accept the value",
  dc_q_lowered: "When a cap lowers it",
  dc_q_ignored: "When Claude Code skips it",
  dc_q_overridden: "When another source wins",
  dc_q_unknown: "When Bar Tab can't tell",
  dc_q_in_effect: "Which value applies",
  dc_q_default: "When nothing sets it",
  dc_checked: "Checked on {version}, {date}",
  dc_due_mark: "Due for a re-check",
  dc_docs_one: "Show the line from the docs",
  dc_docs_other: "Show the {n} lines from the docs",
  dc_new_tab: "opens in a new tab",
  dc_nodocs_tested: "No docs line. Bar Tab's test is the source.",
  dc_nodocs_assumed: "No docs line covers this case.",
  dc_found_in_docs: "Found in a line from the docs",
  dc_none_h: "No rules match “{query}”",
  dc_none_b: "Try a setting name such as effortLevel, a rule id, or a word from the docs.",
  dc_none_glossary: "Look it up in the Glossary",
  dc_err_h: "Bar Tab couldn't load the rules",
  dc_err_b: "The Bar Tab server didn't send them. Try again in a moment.",
  dc_gone_rule_h: "There's no rule called {id}",
  dc_gone_setting_h: "There's no setting called {key}",
  dc_gone_link: "Show every setting",
  dc_due_all_one:
    "Showing the {due} rule. Bar Tab checked it on {checked_on}, before the {installed} you run.",
  dc_due_all_other:
    "Showing all {due} rules. Bar Tab checked each one on {checked_on}, before the {installed} you run.",
  dc_due_some_one:
    "Showing the {due} rule Bar Tab checked on a version older than your {installed}.",
  dc_due_some_other:
    "Showing the {due} rules Bar Tab checked on a version older than your {installed}.",
  dc_due_show_all: "Show all rules",
  dc_due_none_h: "No rules are due",
  dc_due_none_b: "Bar Tab checked every rule on Claude Code {installed} or later.",

  // Glossary (M5 task 3b). Direction A. The list section headings are the glossary.ts terms.
  gl_sub: "The words Bar Tab uses, and what each one means",
  gl_search_label: "Search the glossary",
  gl_search_ph: "A word you saw in Bar Tab",
  gl_count_one: "{n} entry",
  gl_count_other: "{n} entries",
  gl_count_of: "{n} of {total} entries",
  gl_count_ann_one: "{n} entry shown",
  gl_count_ann_other: "{n} entries shown",
  gl_count_ann_of: "{n} of {total} entries shown",
  gl_count_ann_none: "No entries match",
  gl_status_q: "How a setting or item stands",
  gl_scopes_q: "Where a value can be set. The first five rank highest first.",
  gl_conf_q: "How sure Bar Tab is of a rule",
  gl_terms_h: "Terms",
  gl_terms_q: "Every other word, A to Z",
  gl_none_h: "No entries match “{query}”",
  gl_none_b: "Try a shorter word, or search the rules if it names a setting.",
  gl_none_rules: "Search the rules for “{query}”",
  gl_gone_h: "There's no glossary entry called {id}",
  gl_see: "See also",
  // Search counts each rule once, though a rule with several outcomes shows under each one
  dc_results_note:
    "Some rules can lead to more than one status, so they show under each one. The total counts each rule once.",

  // The inspector Why line, when its rule is due (M5 task 3b)
  in_older: "Older than your {installed}",
  in_rule_link: "See the rule {id}",

  // Order ladder layer names. managed, local, project, user and plugin reuse the sc_ names.
  ly_env: "Environment variables",
  ly_flag: "Launch flag",
  ly_cli: "--settings file",
  ly_agent: "Agent file",
  ly_default: "Claude Code's default",
  ly_default_agent: "The main session's model",
} as const;

export type StringKey = keyof typeof en;
