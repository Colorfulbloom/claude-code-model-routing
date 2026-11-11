/*
 * The help registry, one entry per help spot, keyed by id (m5-build.md section 4). A spot names
 * only its id, as <HelpButton help="live.cache" /> or <HelpTerm help="agents.cols" />, and
 * passes the values it shows. HelpId is the type of this object's keys, so an unknown id is a
 * compile error. help.test.ts also fails on an entry no spot names and on a glossary id the
 * Glossary lacks. Words from the tech-writer deck (November 10). Labels and meanings sit in
 * separate fields, because values follow the en.ts lint: no colon, no em dash, no "!".
 */
import type { StringKey } from "@/strings/en";
import type { TermId } from "@/strings/glossary";
import type { ListId } from "@/strings/lists";

/** Where the trigger sits. Tiles, cards and charts get the "?". Columns and fields get the term form. */
export type HelpKind = "tile" | "card" | "chart" | "column" | "field" | "pill" | "other";

export type ChartUnit = "hour" | "day" | "week" | "month";

export interface HelpLine {
  /** The label the line explains, as it reads on screen. */
  readonly label: string;
  /** What it means, starting lower case, as one sentence. */
  readonly means: string;
  /** The name of a value the spot passes in, drawn beside this line. */
  readonly ref?: string;
}

export interface HelpEntry {
  readonly title: string;
  /** Titles that follow the spot's unit, so the popover title matches the card title. */
  readonly titleByUnit?: Readonly<Record<ChartUnit, StringKey>>;
  readonly kind: HelpKind;
  /** What the spot shows. */
  readonly shows?: string;
  /** What its numbers, columns or marks mean. */
  readonly lines?: readonly HelpLine[];
  /** A shared list drawn after the lines (the status words, the scopes). */
  readonly list?: ListId;
  /** How to read it. */
  readonly reading?: string;
  /** Glossary terms this entry links to, at most two. */
  readonly glossary?: readonly TermId[];
}

export const HELP = {
  // Live
  "live.spent": {
    title: "Spent so far",
    kind: "tile",
    shows:
      "The session's cost at API list prices, summed over every priced request. On a subscription you pay a flat fee, so read it as what the same use would cost on the API.",
    lines: [
      {
        label: "Big number",
        means:
          "every priced request in the session so far, and it reads Spent in all once the session ends.",
        ref: "value",
      },
      {
        label: "In the last minute",
        means:
          "priced requests in the 60 seconds before now, and it reads Whole session once the session ends.",
        ref: "delta",
      },
      {
        label: "No price",
        means:
          "requests on a model the price table doesn't list, which are left out, so the real cost is higher.",
        ref: "note",
      },
    ],
    glossary: ["api-rate-estimate", "no-price"],
  },
  "live.tokens": {
    title: "Tokens",
    kind: "tile",
    shows: "Every token the session sent and got back, cache reads included.",
    lines: [
      {
        label: "Big number",
        means: "input, output, cache writes and cache reads, summed over the session.",
        ref: "value",
      },
      {
        label: "In the last minute",
        means: "the same sum for the 60 seconds before now.",
        ref: "delta",
      },
    ],
    reading:
      "Cache reads are counted here but not in the Who is working chart, which shows new tokens only. So this number can run far higher than the chart.",
    glossary: ["tokens", "new-tokens"],
  },
  "live.cache": {
    title: "Read from cache",
    kind: "tile",
    shows: "How much of each prompt came from the prompt cache instead of being sent fresh.",
    lines: [
      {
        label: "Percent",
        means:
          "cache reads divided by cache reads plus cache writes plus fresh input, over the whole session, with output left out.",
        ref: "value",
      },
      {
        label: "In the last minute",
        means: "the same share for the 60 seconds before now.",
        ref: "delta",
      },
    ],
    reading:
      "Higher is cheaper, because a cache read costs about a tenth of fresh input at list prices. A sudden drop usually follows a model switch, a compaction or a break longer than the cache lifetime.",
    glossary: ["read-from-cache", "cache-write"],
  },
  "live.agents": {
    title: "Agents working",
    kind: "tile",
    shows:
      "How many runs are busy right now. A run is one agent doing one job, and the main session counts as one.",
    lines: [
      {
        label: "Big number",
        means: "runs with a request, or a new round, in the last 60 seconds.",
        ref: "value",
      },
      {
        label: "Finished",
        means: "agent runs that stopped once every run they started was done.",
        ref: "delta",
      },
      {
        label: "Runs in all",
        means: "every run so far, and any run that isn't working or finished is idle.",
      },
    ],
    reading: "Once the session ends, the tile reads Agent runs and shows every run it had.",
    glossary: ["run", "run-and-session-states"],
  },
  "live.who": {
    title: "Who is working",
    kind: "chart",
    shows: "The session's new tokens over time, above one row per run.",
    lines: [
      {
        label: "Bars",
        means: "new tokens per minute, colored by model, with cache reads left out.",
      },
      {
        label: "Axis",
        means:
          "on a long session each bar covers several minutes, and the axis label says how many.",
      },
      { label: "Indented row", means: "a run started by the row above it." },
      { label: "Dashed line", means: "Bar Tab doesn't know which run started this one." },
      { label: "Now", means: "a bar that reaches Now belongs to a run that is still working." },
      { label: "Round 2", means: "the run stopped, got a new message and went back to work." },
      {
        label: "Finding starter",
        means:
          "Bar Tab hasn't matched the run to its starter yet, and it keeps looking for five minutes after the run finishes.",
      },
      {
        label: "No starter found",
        means: "Bar Tab stopped looking, so the row sits under the main session.",
      },
    ],
    glossary: ["new-tokens", "started-by"],
  },
  "live.requests": {
    title: "Latest requests",
    kind: "card",
    shows: "The five newest requests in this session.",
    lines: [
      { label: "Time", means: "when the request was logged, to the second." },
      { label: "Agent", means: "the run that sent it." },
      { label: "Model", means: "the model, and the effort when the request names one." },
      { label: "Tokens", means: "every token in that request, cache reads included." },
      {
        label: "Cost",
        means:
          "that one request at API list prices, or No price when the price table doesn't list its model.",
      },
    ],
    reading:
      "These costs are estimates, not your bill. If you're on a subscription, Spent so far explains what they mean for you.",
    glossary: ["request", "api-rate-estimate"],
  },
  "live.modelcheck": {
    title: "Model check",
    kind: "card",
    shows:
      "Each agent's runs in this session, checked against the model and effort its setup asks for.",
    list: "status",
    reading:
      "A row shows the worse status of its model and effort, so start with Invalid and Overridden. Here Overridden also covers runs that used a different value than the setup asks for.",
    glossary: ["model-check", "status-words"],
  },
  "live.status": {
    title: "Run and session states",
    kind: "pill",
    shows: "What a run, or the whole session, is doing now.",
    lines: [
      {
        label: "Working",
        means: "a request, or the start of a new round, in the last 60 seconds.",
      },
      { label: "Idle", means: "no request for over a minute, and not finished yet." },
      { label: "Finished", means: "an agent run stopped, and every run it started is done." },
      { label: "Ended", means: "the session went 30 minutes with no request." },
      {
        label: "Not started yet",
        means: "on Session review, the run starts after the replay line.",
      },
    ],
    reading: "The main session never finishes. It stays Working or Idle until the session ends.",
    glossary: ["run-and-session-states"],
  },
  "live.notices": {
    title: "Updates stopped",
    kind: "other",
    shows: "Why the numbers stopped moving. Live normally updates every second.",
    lines: [
      { label: "Paused at", means: "you pressed Pause, so press Resume to start updates again." },
      {
        label: "Last reached the server at",
        means: "the page lost the Bar Tab server, so the numbers are from that time.",
      },
      { label: "Ended at", means: "the time of the session's last request." },
    ],
    reading: "A session ends after 30 minutes with no request.",
    glossary: ["bar-tab-server", "run-and-session-states"],
  },
  // Summary
  "summary.cost": {
    title: "Cost",
    kind: "tile",
    shows: "What the project's requests in this range would cost at API list prices.",
    lines: [
      { label: "Big number", means: "every priced request in the range.", ref: "value" },
      {
        label: "At least",
        means: "some requests have no price and are left out, so the real cost is higher.",
      },
      {
        label: "Up or Down",
        means:
          "the change from the period just before, which has the same number of days and ends at the same time of day.",
        ref: "delta",
      },
      { label: "Little change", means: "a change under 2 percent." },
      {
        label: "Up or Down with no percent",
        means: "the earlier period isn't complete, so only the direction shows.",
      },
      { label: "Yesterday by a time", means: "on Today, the same hours yesterday." },
      { label: "A day on average", means: "shown when there's nothing earlier to compare with." },
      {
        label: "No price",
        means: "how many requests are left out because the price table doesn't list their model.",
        ref: "note",
      },
    ],
    glossary: ["api-rate-estimate", "comparison-period"],
  },
  "summary.sessions": {
    title: "Sessions",
    kind: "tile",
    shows:
      "Sessions in this project with at least one request in the range, including one that started before it.",
    lines: [
      {
        label: "Up or Down",
        means:
          "the change from the period just before, with the same length and the same time of day.",
        ref: "delta",
      },
      { label: "A day on average", means: "shown when there's nothing earlier to compare with." },
    ],
    glossary: ["session", "comparison-period"],
  },
  "summary.tokens": {
    title: "Tokens",
    kind: "tile",
    shows: "Every token sent and got back in the range, cache reads included.",
    lines: [
      { label: "Big number", means: "input, output, cache writes and cache reads.", ref: "value" },
      { label: "Up or Down", means: "the same comparison as Cost.", ref: "delta" },
    ],
    reading: "Cache reads are cheap, so tokens can climb while cost stays flat.",
    glossary: ["tokens", "comparison-period"],
  },
  "summary.cache": {
    title: "Read from cache",
    kind: "tile",
    shows:
      "The share of prompt tokens that came from the cache, across every request in the range.",
    lines: [
      {
        label: "Percent",
        means:
          "cache reads divided by cache reads plus cache writes plus fresh input, with output left out.",
        ref: "value",
      },
      {
        label: "Points",
        means:
          "the plain difference between two shares, so 62 percent to 70 percent is up 8 points.",
        ref: "delta",
      },
      {
        label: "Up or Down with no number",
        means: "Bar Tab can't compare two whole periods, so only the direction shows.",
      },
      {
        label: "Across every request",
        means: "shown when there's nothing earlier to compare with.",
      },
    ],
    reading: "Higher is cheaper. A drop often follows model switches, compactions or long breaks.",
    glossary: ["read-from-cache", "points"],
  },
  "summary.who": {
    title: "Where the money went",
    kind: "card",
    shows: "Cost per agent in the range. The main session gets its own row.",
    lines: [
      { label: "Amount", means: "the agent's cost at API list prices." },
      { label: "Percent", means: "its share of the range's total cost." },
      {
        label: "Bar",
        means: "its cost next to the costliest agent's, so the top row fills its bar.",
      },
      { label: "Model under the name", means: "the model the agent sent the most requests to." },
    ],
    glossary: ["share", "main-session"],
  },
  "summary.modelcheck": {
    title: "Model check",
    kind: "card",
    shows: "The same check as on Live, over every run in the range.",
    lines: [
      {
        label: "The second number",
        means:
          "agents Bar Tab could check, meaning each one whose file or settings set a model or effort.",
      },
      {
        label: "The first number",
        means:
          "the ones among them that aren't In effect or Default, so it never exceeds the second.",
      },
    ],
    reading:
      "Agents with no agent file, no model or effort set, or no agent type aren't in either number. When every checked agent ran as set, the card asks its question instead of showing a count.",
    glossary: ["model-check", "status-words"],
  },
  "summary.top": {
    title: "Most expensive sessions",
    kind: "card",
    shows:
      "The four costliest sessions in the range. If two cost the same, the one with more tokens ranks higher.",
    lines: [
      { label: "Cost and Tokens", means: "only the requests inside the range." },
      { label: "Bar", means: "each session's cost next to the top session's." },
    ],
    glossary: ["session", "range"],
  },
  "summary.costchart": {
    title: "Cost over time",
    titleByUnit: { hour: "ch_h_hour", day: "ch_h_day", week: "ch_h_week", month: "ch_h_month" },
    kind: "chart",
    shows:
      "Spending over time, one bar per hour, day, week or month. Today shows hours, 7 and 30 days show days, 90 days shows weeks and 12 months shows months. All time picks days for up to 31 days of records, weeks for up to 13 weeks, and months beyond that.",
    lines: [
      { label: "Input", means: "fresh prompt tokens.", ref: "k_input" },
      { label: "Output", means: "what Claude wrote.", ref: "k_output" },
      { label: "Cache read", means: "prompt tokens reused from the cache.", ref: "k_cread" },
      {
        label: "Cache write",
        means: "prompt tokens stored in the cache, 5-minute and 1-hour writes together.",
        ref: "k_cwrite",
      },
      {
        label: "Patterns and colors",
        means: "patterns show the kind of cost, and colors show the model.",
      },
      { label: "So far", means: "the last bar, which is still filling." },
    ],
    reading:
      "Earlier and Later move the chart, but the tiles stay on the range. Weeks start on Monday.",
    glossary: ["cost-kinds", "range"],
  },
  "summary.unpriced": {
    title: "No price note",
    kind: "other",
    shows: "Requests on a model that Bar Tab's price table doesn't list.",
    lines: [
      {
        label: "Count and model",
        means: "how many requests have no price, and which model they used.",
      },
    ],
    reading:
      "These requests are left out of the bars and every cost total, so totals read at least. Bar Tab prices requests when you look, so they get a price as soon as the table lists the model.",
    glossary: ["no-price", "price-source"],
  },
  // Sessions
  "sessions.cols": {
    title: "Sessions table",
    kind: "column",
    shows: "One row per session with a request in the range, grouped by day.",
    lines: [
      {
        label: "Session",
        means: "the start time and git branch, with Working or Idle while the session runs.",
      },
      {
        label: "Agents",
        means: "the agent types that sent requests, the main session included.",
      },
      { label: "Runs", means: "each agent run, plus one for the main session." },
      { label: "Tokens", means: "every token inside the range, cache reads included." },
      { label: "Cost", means: "the requests inside the range, at API list prices." },
    ],
    glossary: ["run", "session"],
  },
  "sessions.before": {
    title: "Started earlier",
    kind: "pill",
    shows:
      "This session began before the range started. Its tokens and cost here count only the part inside the range. Open the session to see all of it.",
    glossary: ["range"],
  },
  "sessions.share": {
    title: "Share bar",
    kind: "other",
    shows:
      "The session's cost next to the costliest session in the list, which fills its bar. The figure beside the bar is the cost.",
  },
  // Agents
  "agents.cols": {
    title: "Agents table",
    kind: "column",
    shows: "What each agent asks for next to what its runs actually used.",
    lines: [
      {
        label: "Set to",
        means:
          "the model and effort in the agent's file, or for the main session, what your settings ask for.",
      },
      { label: "Nothing set", means: "the file sets neither a model nor an effort." },
      {
        label: "Ran with",
        means:
          "the model and effort pair most runs used, with each run counted once under the pair it sent the most requests with.",
      },
      { label: "Also", means: "other pairs some runs used, with how many runs each." },
      { label: "Check", means: "one status word for whether the agent ran as set." },
      {
        label: "Runs",
        means: "every run of the agent in the range, and for the main session one per session.",
      },
      { label: "Cost", means: "the agent's cost in the range at API list prices." },
    ],
    glossary: ["set-to", "ran-with"],
  },
  "agents.check": {
    title: "Check",
    kind: "column",
    shows: "One status word for whether the agent ran as set, the worse of its model and effort.",
    lines: [
      {
        label: "Dash",
        means:
          "there's nothing to check, because the agent has no file, sets neither model nor effort, or has no agent type.",
      },
    ],
    list: "status",
    glossary: ["model-check", "status-words"],
  },
  "agents.unchecked": {
    title: "Not checked",
    kind: "pill",
    shows:
      "Model check doesn't cover agents from a plugin or from managed settings, so this row has no status. Open the agent in Your setup to see where its model and effort come from.",
    glossary: ["plugin-agent", "model-check"],
  },
  "agents.source": {
    title: "Where an agent comes from",
    kind: "other",
    shows: "Where the agent's file lives.",
    lines: [
      { label: "User", means: "your own agents folder, used in every project." },
      { label: "Shared project", means: "the project's .claude/agents folder." },
      {
        label: "Settings",
        means: "the main session, which takes its model and effort from settings files.",
      },
      { label: "Plugin", means: "an installed plugin, named after the word." },
      { label: "Managed", means: "your organization's managed setup." },
      {
        label: "Source unknown",
        means: "Bar Tab found no user or project file for this agent type.",
      },
    ],
    glossary: ["scopes", "plugin-agent"],
  },
  "agents.inspector": {
    title: "Agent details",
    kind: "field",
    shows: "The agent's file as written, and how much it ran.",
    lines: [
      {
        label: "Run line",
        means: "runs, sessions and cost over the page's range, or the last 30 days in Your setup.",
      },
      {
        label: "Runs on",
        means: "the model and effort its runs should use once caps and overrides apply.",
      },
      {
        label: "Fields Claude Code ignores here",
        means: "hooks, MCP servers and permission mode, which plugin agents can't use.",
      },
    ],
    glossary: ["front-matter", "plugin-agent"],
  },
  // Models
  "models.cols": {
    title: "Models table",
    kind: "column",
    shows: "What each model cost in the range, and who used it.",
    lines: [
      {
        label: "Share",
        means: "the model's cost as a percent of the range total, with <1% for under one percent.",
      },
      { label: "Tokens", means: "every token, cache reads included." },
      {
        label: "From cache",
        means:
          "the Read from cache share for this model only, with a dash when there's nothing to compare.",
      },
      { label: "Used by", means: "the agents that sent it requests." },
    ],
    glossary: ["share", "read-from-cache"],
  },
  "models.kinds": {
    title: "What the cost is made of",
    kind: "card",
    shows: "Each model's cost, split into four kinds of token.",
    reading:
      "Lots of cache reads next to small cache writes means the cache is doing its job. If cache writes stay large, the start of the prompt keeps changing, so the cache gets rebuilt instead of reused.",
    glossary: ["cost-kinds", "cache-write"],
  },
  "models.chart": {
    title: "Cost kinds",
    kind: "chart",
    shows: "One bar per model, split by the kind of token it paid for.",
    lines: [
      { label: "Input", means: "fresh prompt tokens." },
      { label: "Output", means: "what Claude wrote, the priciest kind." },
      {
        label: "Cache read",
        means: "reused prompt tokens, at about a tenth of the input price.",
      },
      {
        label: "Cache write",
        means:
          "prompt tokens stored for reuse, which cost more than input, and more again for the 1-hour lifetime than the 5-minute one.",
      },
      {
        label: "Patterns and colors",
        means: "patterns show the kind of cost, and colors show the model.",
      },
    ],
    glossary: ["cost-kinds", "cache-write"],
  },
  // Session review
  "review.tiles": {
    title: "Session totals",
    kind: "tile",
    shows:
      "The session as it stood at the replay line, with the whole-session figure under each number.",
    lines: [
      {
        label: "Figure under the number",
        means:
          "the same number for the whole session, or the whole session so far while it still runs.",
      },
      {
        label: "Ring",
        means:
          "fills to the Read from cache percent, an estimate until the line reaches the end, where it becomes exact.",
      },
      {
        label: "Dots",
        means:
          "one filled dot per working run and one ringed check per finished run, up to eight, then +n.",
      },
      { label: "Runs", means: "every run at the line, the main session included." },
    ],
    glossary: ["replay-line", "run"],
  },
  "review.timeline": {
    title: "Who worked when",
    kind: "chart",
    shows: "The same chart and rows as Who is working on Live, for this session.",
    lines: [
      {
        label: "Bars",
        means: "new tokens per minute, colored by model, with cache reads left out.",
      },
      { label: "Hollow bars", means: "work that comes after the replay line." },
      {
        label: "Starts later",
        means: "runs under this row that begin after the line, hidden until you choose Show.",
      },
      { label: "Since", means: "when the run started." },
    ],
    glossary: ["new-tokens", "replay-line"],
  },
  "review.status": {
    title: "Session states",
    kind: "pill",
    shows: "Where the session stands at the replay line.",
    lines: [
      { label: "Working", means: "a request in the last 60 seconds." },
      { label: "Idle", means: "no request for over a minute, but for less than 30 minutes." },
      { label: "Ended", means: "30 minutes with no request." },
    ],
    glossary: ["run-and-session-states", "session"],
  },
  // Your setup
  "setup.map": {
    title: "Your setup table",
    kind: "column",
    shows: "One row for each part of what Claude Code loads.",
    lines: [
      {
        label: "Part",
        means: "one kind of thing Claude Code loads, such as settings, agents or hooks.",
      },
      { label: "What applies", means: "a short summary of what's in effect for this project." },
      {
        label: "Status",
        means:
          "one word for each status found among the part's items, with a dash when the part is empty or Bar Tab can't see it.",
      },
    ],
    list: "status",
    reading:
      "In effect and Default are fine. Overridden usually is too, because higher scopes are meant to win. Look into Invalid, Ignored and Unknown.",
    glossary: ["part", "status-words"],
  },
  "setup.card": {
    title: "What shapes a session",
    kind: "card",
    shows:
      "Settings, agents, instructions, rules files, skills, hooks, permissions, MCP servers, plugins and output style, as Claude Code finds them for this project.",
    reading:
      "Bar Tab reads only files on this computer. Command-line flags, and shell changes made after Bar Tab started, don't show here.",
    glossary: ["part", "scopes"],
  },
  "setup.unlisted": {
    title: "Project not on the list",
    kind: "other",
    shows:
      "Bar Tab reads project files only for projects on its list. This one shows its usage history plus your user and managed setup, so its project scopes say Not read here.",
    glossary: ["project-list"],
  },
  "setup.scopes": {
    title: "Scopes",
    kind: "field",
    shows:
      "The places a value can be set, highest first. When two set the same key, the higher one wins.",
    list: "scopes",
    reading:
      "Plugin and Your shell aren't levels. A plugin adds items of its own, and for some keys, such as ANTHROPIC_MODEL, a shell variable beats every settings file.",
    glossary: ["scopes", "precedence"],
  },
  "setup.where": {
    title: "Where it's set, top wins",
    kind: "field",
    shows: "Every place that sets this item, with the winner on top.",
    lines: [
      {
        label: "Row",
        means: "the scope, the file and line, the value, and that row's own status.",
      },
      {
        label: "Not visible here",
        means: "a scope Bar Tab can't read, such as the command line.",
      },
      {
        label: "Not read here",
        means: "a project file Bar Tab skips, because the project isn't on its list.",
      },
      { label: "Not set when Bar Tab started", means: "your shell had no value for it then." },
    ],
    reading:
      "If the top row isn't the one you edited, that higher scope is why your change has no effect. List settings such as permission rules combine across scopes instead.",
    glossary: ["precedence", "scopes"],
  },
  "setup.why": {
    title: "Why",
    kind: "field",
    shows: "The reason for this item's status, and how sure Bar Tab is of the rule behind it.",
    list: "confidence",
    reading:
      "Confidence rates Bar Tab's rule, not your file. Each rule names the Claude Code version it was checked on, and the Why line opens it in How Claude Code decides.",
    glossary: ["confidence-words"],
  },
  "setup.inspector.status": {
    title: "Status",
    kind: "pill",
    list: "status",
    reading: "Overridden isn't a problem by itself, so To fix never lists it.",
    glossary: ["status-words", "to-fix"],
  },
  "setup.applies": {
    title: "When a change applies",
    kind: "field",
    shows: "When an edit to this item reaches Claude Code.",
    lines: [
      { label: "Applies right away", means: "Claude Code picks up the change while it runs." },
      { label: "Applies to new sessions", means: "sessions already running keep the old value." },
      {
        label: "Applies after you restart Claude Code",
        means: "the change waits until Claude Code starts again.",
      },
      {
        label: "Applies after plugins reload",
        means:
          "the change reaches a running session after you run /reload-plugins, or in a new session.",
      },
    ],
    glossary: ["when-a-change-applies"],
  },
  "setup.imports": {
    title: "Imports",
    kind: "field",
    shows: "Files this one pulls in with @ imports, in load order.",
    lines: [
      { label: "Loaded", means: "Claude Code reads it." },
      { label: "File not found", means: "the path leads nowhere, so Claude Code skips it." },
      {
        label: "Already in the chain",
        means: "the import loops back to a file that already loaded, so it doesn't load twice.",
      },
      { label: "Past 4 hops", means: "the import is too deep, so it doesn't load." },
      {
        label: "Not read here",
        means:
          "the file is outside the folders Bar Tab reads, though Claude Code may still load it.",
      },
    ],
    glossary: ["import"],
  },
  "setup.hooks": {
    title: "Hooks",
    kind: "field",
    shows: "When the hook runs, what sets it off, and what it does.",
    lines: [
      { label: "Event", means: "the point in a session where it fires." },
      {
        label: "Matches",
        means: "what the hook reacts to, such as a tool name for tool events.",
      },
      {
        label: "Every time",
        means: "there's no matcher, so it fires on every occurrence of the event.",
      },
      {
        label: "Does",
        means: "what it does when it fires, such as run a command or send an HTTP request.",
      },
      { label: "Timeout", means: "how many seconds Claude Code waits for it." },
    ],
    glossary: ["hook-event"],
  },
  "setup.permissions": {
    title: "Permissions",
    kind: "field",
    shows: "What each rule lets Claude do, and the mode a session starts in.",
    lines: [
      { label: "Allowed without asking", means: "matching calls run with no prompt." },
      { label: "Asks you first", means: "you get a prompt each time." },
      { label: "Blocked", means: "the call never runs." },
      { label: "Mode", means: "the permission mode a new session starts in." },
    ],
    reading:
      "An allow rule can't make an exception to a deny rule, because deny rules are checked first. Auto and bypass modes don't take effect from project or local settings. Allow rules in project settings wait until you trust the folder.",
    glossary: ["permission-mode"],
  },
  "setup.mcp": {
    title: "MCP servers",
    kind: "field",
    shows: "How Claude Code reaches this server, and whether it's approved.",
    lines: [
      {
        label: "A local command (stdio)",
        means: "a program on this computer that Claude Code starts.",
      },
      { label: "HTTP and WebSocket", means: "a remote server." },
      {
        label: "Server-sent events (SSE)",
        means: "an older remote transport that Claude Code's docs mark as deprecated.",
      },
      {
        label: "Approved",
        means:
          "for servers in the project's .mcp.json, Yes means a setting or your answer to Claude Code's prompt approved it, and No means Claude Code skips it until you do.",
      },
    ],
    glossary: ["mcp-server"],
  },
  "setup.plugins": {
    title: "Plugins",
    kind: "field",
    shows: "Whether the plugin is on, and where.",
    lines: [
      { label: "On", means: "a settings file turns it on." },
      { label: "On in", means: "the scopes whose settings turn it on." },
      { label: "Off", means: "it's installed, but nothing turns it on." },
      {
        label: "Old versions on disk",
        means:
          "folders of earlier versions Claude Code has replaced, which it removes 14 days later.",
      },
    ],
    glossary: ["plugin"],
  },
  "setup.readonly": {
    title: "Can't change here",
    kind: "other",
    shows:
      "Why Bar Tab leaves this item alone, and where to change it instead. The reason names the owner, such as your organization, a plugin, a launch flag or Claude Code's own config file.",
    glossary: ["read-only"],
  },
  "setup.unread": {
    title: "Couldn't read",
    kind: "other",
    shows:
      "Files in this part that Bar Tab couldn't open. Common causes are file permissions, text that isn't UTF-8, a file over 1 MB, or a file removed partway through the read.",
    reading:
      "Anything those files set is missing here, so statuses may change once Bar Tab can read them. The 1 MB limit is Bar Tab's, not Claude Code's.",
    glossary: ["couldnt-read"],
  },
  // To fix
  "fix.groups": {
    title: "Problem groups",
    kind: "other",
    shows: "Problems in this project, sorted by what kind of problem they are.",
    lines: [
      { label: "Couldn't read", means: "files Bar Tab couldn't open." },
      { label: "Won't load", means: "items Claude Code skips." },
      { label: "Not as set", means: "items that run differently than they're set." },
      { label: "Can't tell", means: "items where Bar Tab can't tell what applies." },
      { label: "Notices", means: "things worth knowing that aren't problems in your setup." },
    ],
    reading:
      "Only the first three make up the To fix count. Overridden settings never show up here, because a higher scope winning is how Claude Code is meant to work.",
    glossary: ["to-fix"],
  },
  "fix.rows": {
    title: "Problem row",
    kind: "other",
    shows:
      "One problem per row. It says what's wrong, which file and line cause it, and what happens as a result.",
    lines: [
      { label: "Open", means: "shows the item in Your setup." },
      {
        label: "Copy path or Copy command",
        means: "gives you the text to use yourself, and Bar Tab never runs a command.",
      },
      {
        label: "Can't fix here",
        means:
          "the cause is in a managed file, a plugin or a place Bar Tab can't see, or at the limit of how far Bar Tab looks.",
      },
    ],
    glossary: ["to-fix", "read-only"],
  },
  // Shell
  "shell.nav": {
    title: "To fix count",
    kind: "other",
    shows:
      "Problems in this project that Bar Tab counts, meaning Couldn't read, Won't load and Not as set. Can't tell and Notices aren't counted.",
    glossary: ["to-fix"],
  },
  "shell.updated": {
    title: "Updated",
    kind: "other",
    shows:
      "When this tab last got an answer from the Bar Tab server. It shows only while the tab is trying to reconnect, so numbers on the page may be older than they look. No answer yet means none has arrived since the tab opened.",
    glossary: ["bar-tab-server"],
  },
  "shell.demo": {
    title: "Demo data",
    kind: "other",
    shows:
      "Bar Tab is showing sample sessions it built, not your own Claude Code transcripts. Every number on the page is made up.",
    glossary: ["demo-data"],
  },
  "shell.projectstate": {
    title: "Project state",
    kind: "pill",
    shows: "Whether Bar Tab can find this project's folder and its .claude folder.",
    list: "project_state",
    glossary: ["project-list"],
  },
  "shell.range": {
    title: "Range",
    kind: "other",
    shows:
      "The days the Review pages cover. Ranges count local days and end today. Today starts at midnight, and 12 months means 365 days.",
    lines: [
      {
        label: "Compared with",
        means: "the same number of days just before, up to the same time of day.",
      },
      {
        label: "All time",
        means: "everything since your first recorded request, with nothing to compare against.",
      },
    ],
    glossary: ["range", "comparison-period"],
  },
  "shell.prices": {
    title: "Prices as of",
    kind: "other",
    shows: "Which price table Bar Tab uses for every cost.",
    lines: [
      {
        label: "Prices as of a date",
        means:
          "a LiteLLM copy fetched in the last 48 hours, and Bar Tab checks for a new one once a day.",
      },
      {
        label: "Saved prices",
        means: "the last good copy, because the newest fetch failed or none ran in 48 hours.",
      },
      {
        label: "Bundled prices",
        means: "the copy that ships with Bar Tab, used until a fetch succeeds.",
      },
      { label: "Custom prices", means: "your organization's modelPricing setting." },
    ],
    glossary: ["price-source", "api-rate-estimate"],
  },
  "shell.backup": {
    title: "Last backup",
    kind: "other",
    shows:
      "When Bar Tab last copied your saved history. It makes a copy at least once a day, and another when it stops cleanly unless the last one is under an hour old.",
    lines: [
      {
        label: "Backup failed at",
        means: "the newest copy didn't finish, but your saved history isn't affected.",
      },
    ],
    reading:
      "Bar Tab keeps seven good copies. It checks each new one first, so a failed copy never replaces a good one.",
    glossary: ["backup"],
  },

  // M6 Edit core
  "edit.save": {
    title: "This save",
    kind: "card",
    shows:
      "What Bar Tab will write when you press Save, read from the file just now. It updates each time you change the value.",
    lines: [
      {
        label: "File",
        means: "the file this save writes, with the real file beside it when the path is a link.",
      },
      { label: "Set to", means: "the value in that file now, and the value after the save." },
      {
        label: "Runs at",
        means:
          "what Claude Code runs now and what it would run after the save, each with its status.",
      },
      {
        label: "Minus and plus lines",
        means: "the lines the save removes and adds, at their real line numbers.",
      },
      {
        label: "Bar Tab read this file at",
        means:
          "when Bar Tab read the file for this preview, so a change after that time stops the save.",
      },
    ],
    reading:
      "Save waits until this card matches your latest choice, so you always see the change before Bar Tab writes it. Bar Tab keeps a copy of the old file first, so Undo can put it back.",
    glossary: ["when-a-change-applies", "set-to"],
  },
  "edit.scopes": {
    title: "Save to",
    kind: "field",
    shows: "The files this value can go in, and what would happen if you saved it there.",
    lines: [
      {
        label: "Takes effect",
        means: "a value saved here is the one Claude Code uses for this project.",
      },
      {
        label: "Overridden by",
        means:
          "a higher scope sets this too, so a value saved here changes nothing in this project.",
      },
      { label: "set now", means: "the file that holds the current value." },
      {
        label: "links to",
        means: "the file is a link, so the save changes the file it points to.",
      },
    ],
    list: "scopes",
    reading:
      "User reaches every project, so This save lists the other projects it changes. When git tracks the file, This save says so, because others get the change once you push it.",
    glossary: ["scopes", "precedence"],
  },
  "edit.history": {
    title: "Changes",
    kind: "card",
    shows:
      "Every save Bar Tab made for this project, newest first, with what Undo can do for each one.",
    lines: [
      { label: "Change", means: "the setting or agent, with its old and new value." },
      {
        label: "File",
        means: "the scope and the file, plus the real file when the path is a link.",
      },
      { label: "Can undo", means: "Undo puts the old file back." },
      {
        label: "File changed since",
        means:
          "another program changed the file after the save, so Undo shows what it would remove first.",
      },
      { label: "Undo deletes the file", means: "the save made a new file, so Undo removes it." },
      { label: "Undone at", means: "this save was already undone at that time." },
    ],
    reading: "This page works with editing off. Only Undo needs editing on.",
  },
  "shell.editing": {
    title: "Editing in Bar Tab",
    kind: "other",
    shows:
      "Whether this Bar Tab can change your files. Editing is off unless Bar Tab starts with --allow-edits.",
    lines: [
      {
        label: "Editing on",
        means: "Bar Tab can save changes to your settings files and undo its own saves.",
      },
      {
        label: "Editing off",
        means:
          "every page still shows your setup and Changes still lists past saves, but Edit and Undo stay off.",
      },
    ],
    reading:
      "To turn editing on, add --allow-edits to the command you start Bar Tab with. If Bar Tab is already running with editing off, that restarts it with editing on, and open pages ask you to reload. To turn editing off, stop Bar Tab, then start it without --allow-edits.",
    glossary: ["bar-tab-server"],
  },
} as const satisfies Readonly<Record<string, HelpEntry>>;

export type HelpId = keyof typeof HELP;

export function helpEntry(id: HelpId): HelpEntry {
  return HELP[id];
}
