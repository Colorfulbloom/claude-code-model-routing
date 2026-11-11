/*
 * The Glossary, typed once (plan-a section 3, m5-build.md section 4). Terms are keyed by id, and
 * the id is the route segment, #/reference/glossary/<id>. A term with `list` shows that shared
 * list under its meaning, so the status words, scopes and confidence words are written only in
 * lists.ts. Help entries link here by term id, and help.test.ts fails on an id that is missing.
 * Words from the tech-writer deck (November 10). Values follow the en.ts lint: no colon, no em
 * dash, no exclamation mark.
 */
import type { ListId } from "@/strings/lists";

export type GlossaryGroup = "status" | "scopes" | "confidence" | "terms";

export interface GlossaryTerm {
  /** The term as the app shows it. */
  readonly term: string;
  /** What it means, in one or two sentences. */
  readonly means: string;
  readonly group: GlossaryGroup;
  /** A shared list drawn under the meaning. */
  readonly list?: ListId;
  /** Related terms, by id. */
  readonly see?: readonly string[];
}

export const GLOSSARY = {
  // Sections drawn from the shared lists
  "status-words": {
    term: "Status words",
    means:
      "Seven words for how a setting or item stands, such as whether it applies or something else wins. Model check, the Agents table and Your setup all use them.",
    group: "status",
    list: "status",
    see: ["model-check", "confidence-words"],
  },
  scopes: {
    term: "Scopes",
    means:
      "The places Claude Code reads a value from, highest first. When two set the same key, the higher one wins.",
    group: "scopes",
    list: "scopes",
    see: ["precedence"],
  },
  "confidence-words": {
    term: "Confidence words",
    means:
      "How sure Bar Tab is of a rule it applies. Each rule carries one word and names the Claude Code version it was checked on.",
    group: "confidence",
    list: "confidence",
    see: ["status-words"],
  },
  // Terms, A to Z
  "api-rate-estimate": {
    term: "API-rate estimate",
    means: "A cost worked out from the tokens used at API list prices. It isn't your bill.",
    group: "terms",
    see: ["price-source", "no-price"],
  },
  backup: {
    term: "Backup",
    means:
      "A copy of your saved history that Bar Tab makes at least once a day. It keeps the seven newest good copies.",
    group: "terms",
  },
  "bar-tab-server": {
    term: "Bar Tab server",
    means:
      "The program on this computer that reads your transcripts and answers this page. When the page can't reach it, the numbers stop updating.",
    group: "terms",
  },
  "cache-write": {
    term: "Cache write",
    means:
      "Prompt tokens stored in the prompt cache so later requests can read them for less. A write costs more than plain input, and the 1-hour lifetime costs more than the 5-minute one.",
    group: "terms",
    see: ["cost-kinds", "read-from-cache"],
  },
  "comparison-period": {
    term: "Comparison period",
    means:
      "The stretch of time a range is compared with, the same number of days just before it, up to the same time of day. All time has none.",
    group: "terms",
    see: ["range"],
  },
  "cost-kinds": {
    term: "Cost kinds",
    means:
      "The four kinds of token a cost is made of, Input, Output, Cache read and Cache write. Each has its own price.",
    group: "terms",
    see: ["cache-write", "tokens"],
  },
  "couldnt-read": {
    term: "Couldn't read",
    means:
      "A file Bar Tab couldn't open, because of file permissions, text that isn't UTF-8, a size over 1 MB, or a file removed while Bar Tab read it. Anything that file sets is missing from Your setup until Bar Tab can read it.",
    group: "terms",
    see: ["to-fix"],
  },
  "demo-data": {
    term: "Demo data",
    means:
      "Sample sessions Bar Tab builds to show how its pages work. None of it comes from your Claude Code transcripts.",
    group: "terms",
  },
  "front-matter": {
    term: "Front matter",
    means:
      "The YAML block at the top of an agent, skill or rules file. It holds fields such as name, description, model and effort.",
    group: "terms",
    see: ["plugin-agent"],
  },
  "hook-event": {
    term: "Hook event",
    means:
      "The point in a session where a hook runs, such as before a tool call or when a session starts.",
    group: "terms",
  },
  import: {
    term: "Import",
    means:
      "An @ line in a CLAUDE.md file that pulls in another file. Claude Code follows imports up to 4 hops deep.",
    group: "terms",
  },
  "main-session": {
    term: "Main session",
    means:
      "The Claude Code conversation you type into. It counts as one run in each session, and it never finishes while the session runs.",
    group: "terms",
    see: ["run", "session"],
  },
  "mcp-server": {
    term: "MCP server",
    means:
      "A server that gives Claude more tools, started as a local command or reached over the network. MCP stands for Model Context Protocol.",
    group: "terms",
    see: ["plugin"],
  },
  "model-check": {
    term: "Model check",
    means:
      "Bar Tab's check of whether each agent ran on the model and effort its setup asks for. Each row gets one status word, the worse of its model and effort.",
    group: "terms",
    see: ["status-words", "set-to"],
  },
  "new-tokens": {
    term: "New tokens",
    means:
      "Input, output and cache writes, with cache reads left out. The Who is working and Who worked when charts show them.",
    group: "terms",
    see: ["tokens"],
  },
  "no-price": {
    term: "No price",
    means:
      "A request on a model Bar Tab's price table doesn't list. It's left out of every cost, so totals read at least, and it gets a price once the table lists the model.",
    group: "terms",
    see: ["price-source", "api-rate-estimate"],
  },
  part: {
    term: "Part",
    means:
      "One kind of thing Claude Code loads for a session, such as settings, agents, hooks or MCP servers. Your setup has one row per part.",
    group: "terms",
    see: ["scopes"],
  },
  "permission-mode": {
    term: "Permission mode",
    means:
      "The mode a new session starts in, which decides how often Claude Code asks before it acts. A settings file sets it with defaultMode.",
    group: "terms",
  },
  plugin: {
    term: "Plugin",
    means:
      "A package that adds agents, skills, hooks, MCP servers, output styles or settings to Claude Code. A settings file turns it on.",
    group: "terms",
    see: ["plugin-agent"],
  },
  "plugin-agent": {
    term: "Plugin agent",
    means:
      "An agent that comes with an installed plugin. Model check doesn't cover it, and Claude Code ignores its hooks, MCP servers and permission mode fields.",
    group: "terms",
    see: ["plugin", "model-check"],
  },
  points: {
    term: "Points",
    means:
      "The plain difference between two percents. Going from 62 percent to 70 percent is up 8 points, not up 13 percent.",
    group: "terms",
    see: ["read-from-cache"],
  },
  precedence: {
    term: "Precedence",
    means:
      "The order that decides which scope wins when two set the same key. Bar Tab shows it as Where it's set, top wins, and list settings such as permission rules combine instead.",
    group: "terms",
    see: ["scopes"],
  },
  "price-source": {
    term: "Price source",
    means:
      "Where Bar Tab's prices come from. In order, that's your organization's custom prices, a LiteLLM copy fetched in the last 48 hours, the last good copy, or the copy that ships with Bar Tab.",
    group: "terms",
    see: ["api-rate-estimate", "no-price"],
  },
  "project-list": {
    term: "Project list",
    means:
      "The projects Bar Tab reads setup files for. A project that isn't on it still shows its usage history, with only your user and managed setup.",
    group: "terms",
    see: ["scopes"],
  },
  "ran-with": {
    term: "Ran with",
    means:
      "The model and effort pair an agent's runs actually used. Each run counts once, under the pair it sent the most requests with.",
    group: "terms",
    see: ["set-to", "model-check"],
  },
  range: {
    term: "Range",
    means:
      "The days the Review pages cover, from Today to All time. Ranges count local days and end today.",
    group: "terms",
    see: ["comparison-period"],
  },
  "read-from-cache": {
    term: "Read from cache",
    means:
      "The share of prompt tokens that came from the prompt cache, which is cache reads divided by cache reads, cache writes and fresh input. Output isn't part of it.",
    group: "terms",
    see: ["cache-write", "points"],
  },
  "read-only": {
    term: "Read only",
    means:
      "An item Bar Tab can't change, because your organization, a plugin, a launch flag or Claude Code's own config file owns it. The item says where to change it instead.",
    group: "terms",
    see: ["scopes"],
  },
  "replay-line": {
    term: "Replay line",
    means:
      "The line you drag on Session review to replay a session minute by minute. The numbers and bars show the session as it stood at that time.",
    group: "terms",
    see: ["run-and-session-states"],
  },
  request: {
    term: "Request",
    means:
      "One call Claude Code makes to a model, with its own tokens and cost. Bar Tab reads requests from Claude Code's session transcripts.",
    group: "terms",
    see: ["tokens", "session"],
  },
  round: {
    term: "Round",
    means:
      "A run's next stretch of work after it stopped and got a new message. Rows label them Round 2, Round 3 and so on.",
    group: "terms",
    see: ["run"],
  },
  run: {
    term: "Run",
    means:
      "One agent doing one job, from its first request until it finishes. The main session counts as one run in each session.",
    group: "terms",
    see: ["main-session", "round"],
  },
  "run-and-session-states": {
    term: "Run and session states",
    means:
      "Working, Idle, Finished, Ended and Not started yet say what a run or a session is doing at the moment. Only agent runs finish, and a session ends after 30 minutes with no request.",
    group: "terms",
    see: ["run", "session"],
  },
  session: {
    term: "Session",
    means:
      "One Claude Code conversation, with every run in it. It ends after 30 minutes with no request.",
    group: "terms",
    see: ["run", "main-session"],
  },
  "set-to": {
    term: "Set to",
    means:
      "The model and effort an agent's file asks for. For the main session, it's what your settings ask for.",
    group: "terms",
    see: ["ran-with", "model-check"],
  },
  share: {
    term: "Share",
    means:
      "One part's cost as a percent of the total cost in the range. Under one percent reads <1%.",
    group: "terms",
  },
  "started-by": {
    term: "Started by",
    means:
      "The run that launched this one. Its row sits indented under its starter, and a dashed line means Bar Tab doesn't know the starter.",
    group: "terms",
    see: ["run"],
  },
  "to-fix": {
    term: "To fix",
    means:
      "Problems in your setup that Bar Tab counts, in three groups, Couldn't read, Won't load and Not as set. Can't tell and Notices show on the page but aren't counted.",
    group: "terms",
    see: ["couldnt-read"],
  },
  tokens: {
    term: "Tokens",
    means:
      "Every token a request sends and gets back, input, output, cache writes and cache reads together.",
    group: "terms",
    see: ["new-tokens", "cost-kinds"],
  },
  "when-a-change-applies": {
    term: "When a change applies",
    means:
      "When an edit to a setup item reaches Claude Code. That's right away, in new sessions, after a restart, or after plugins reload.",
    group: "terms",
    see: ["plugin"],
  },
} as const satisfies Readonly<Record<string, GlossaryTerm>>;

export type TermId = keyof typeof GLOSSARY;

/** True when the Glossary has this term, so a help link to it can render. */
export function hasTerm(id: string): id is TermId {
  return Object.hasOwn(GLOSSARY, id);
}
