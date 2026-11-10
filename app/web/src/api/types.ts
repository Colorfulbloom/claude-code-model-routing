/*
 * Types for the M0 reads and the access swap. The server's generated schema (schema.d.ts, from
 * openapi.json) is the source of truth, so the names below only re-export it. Hand types stay
 * only for things the client invents, such as the refusal codes it reads from error bodies.
 */
import type { components } from "@/api/schema";

type Schemas = components["schemas"];

/** GET /api/app?project=KEY */
export type AppInfo = Schemas["AppInfo"];
export type Ingest = Schemas["Ingest"];
export type IngestState = Ingest["state"];
export type IngestError = Schemas["IngestError"];
export type IngestErrorCode = IngestError["code"];
export type RunningSession = Schemas["RunningItem"];

export type History = Schemas["HistoryInfo"];
export type PassError = Schemas["PassError"];
export type BackupFailure = Schemas["BackupFailure"];

/** GET /api/prices */
export type PricesAnswer = Schemas["PricesInfo"];
export type PriceSource = PricesAnswer["source"];

/** One project in the picker. */
export type Project = Schemas["Project"];
export type ProjectState = Project["state"];

/** GET /api/projects */
export type ProjectsAnswer = Schemas["ProjectList"];

/** POST /api/access/swap, status 200 */
export type SwapAnswer = Schemas["SwapResponse"];

/** The one error envelope. */
export type ErrorEnvelope = Schemas["ErrorEnvelope"];

/** POST /api/access/swap, status 403. The schema types the body as a plain envelope. */
export interface SwapRefusal {
  code: "code_used" | "code_expired" | "code_unknown" | "server_restarted";
}

/** Any 401 from a call that needs the key. */
export interface KeyRefusal {
  code: "no_key" | "bad_key";
}

/** GET /api/sessions/{id}/timeline?project=KEY, the full answer. */
export type Timeline = Schemas["Timeline"];
export type TimelineRun = Schemas["TimelineRun"];
export type TimelineSession = Schemas["TimelineSession"];
export type TimelineBucket = Schemas["TimelineBucket"];
export type TimelineRound = Schemas["Round"];
export type StateAt = Schemas["StateAt"];
export type Unpriced = Schemas["Unpriced"];
export type LatestRequest = Schemas["LatestRequest"];
export type ModelCheck = Schemas["ModelCheck"];
export type ModelCheckRow = Schemas["ModelCheckRow"];

/** The short answer when the asked etag still matches. */
export type Unchanged = Schemas["Unchanged"];

/** GET /api/live/sessions?project=KEY, the full answer and the short one. */
export type LiveSessions = Schemas["LiveSessions"];
export type LiveSessionsUnchanged = Schemas["LiveSessionsUnchanged"];
export type LiveSession = Schemas["LiveSession"];
export type EndedSession = Schemas["EndedSession"];

/** The Review reads. Every one takes a range, and every answer carries the same window. */
export type Summary = Schemas["Summary"];
export type CostChart = Schemas["CostChart"];
export type SessionList = Schemas["SessionList"];
export type AgentList = Schemas["AgentList"];
export type ModelList = Schemas["ModelList"];
export type ReviewRange = Summary["range"];
export type ReviewWindow = Schemas["ReviewWindow"];
export type ReviewSession = Schemas["ReviewSession"];
export type SessionDay = Schemas["SessionDay"];
export type ChartWindow = Schemas["ChartWindow"];
export type CardError = Schemas["CardError"];
