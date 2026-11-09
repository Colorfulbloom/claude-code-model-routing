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
