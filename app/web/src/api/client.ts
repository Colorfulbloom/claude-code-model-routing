/*
 * The API client and its TanStack Query hooks. Every call carries X-Bartab-Key. A 401 moves the
 * tab to the locked page and three network failures in a row move it to the server stopped page.
 * Any answer, even a refusal, resets the failure count and sets lastAnswerAt. Swap refusals
 * (403) are handled by the access client.
 */
import { createContext, use } from "react";
import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import { isLockReason } from "@/app/access";
import type { Access, LockReason } from "@/app/access";
import type { Connection } from "@/lib/connection";
import type { AppInfo, ProjectsAnswer } from "@/api/types";

export const FAILURES_TO_STOP = 3;
export const APP_POLL_MS = 10_000;
export const INGEST_POLL_MS = 1_000;
export const PROJECTS_POLL_MS = 60_000;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null) {
    super(code ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** The server did not answer: the request failed or came back as a 5xx. */
export class NetworkError extends Error {
  constructor(message = "No answer from the server") {
    super(message);
    this.name = "NetworkError";
  }
}

export interface ApiClient {
  access: Access;
  connection: Connection;
  getApp: (project: string | null, signal?: AbortSignal) => Promise<AppInfo>;
  getProjects: (signal?: AbortSignal) => Promise<ProjectsAnswer>;
}

export interface ApiClientOptions {
  access: Access;
  connection: Connection;
  fetchFn?: typeof fetch;
  now?: () => number;
}

/** Maps a 401 code to the locked page reason. A bad key means this tab's key is stale. */
export function reasonFor401(code: unknown): LockReason {
  if (code === "no_key") return "no_key";
  if (isLockReason(code)) return code;
  return "server_restarted";
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const { access, connection } = options;
  const fetchFn = options.fetchFn ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const now = options.now ?? (() => Date.now());

  function failed(): void {
    if (connection.recordFailure() >= FAILURES_TO_STOP) access.setStopped();
  }

  async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
    const headers: Record<string, string> = {};
    const key = access.getReadKey();
    if (key !== null) headers["X-Bartab-Key"] = key;
    let response: Response;
    try {
      response = await fetchFn(path, signal ? { headers, signal } : { headers });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      failed();
      throw new NetworkError();
    }
    if (response.status >= 500) {
      failed();
      throw new NetworkError(`HTTP ${response.status}`);
    }
    connection.recordAnswer(now());
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    const code =
      typeof body === "object" && body !== null && "code" in body && typeof body.code === "string"
        ? body.code
        : null;
    if (response.status === 401) {
      access.lock(reasonFor401(code));
      throw new ApiError(401, code);
    }
    if (!response.ok) throw new ApiError(response.status, code);
    return body as T;
  }

  return {
    access,
    connection,
    async getApp(project, signal) {
      const query = project === null ? "" : `?project=${encodeURIComponent(project)}`;
      const info = await request<AppInfo>(`/api/app${query}`, signal);
      access.serverAnswered(info.instance);
      return info;
    },
    getProjects(signal) {
      return request<ProjectsAnswer>("/api/projects", signal);
    },
  };
}

export const ApiContext = createContext<ApiClient | null>(null);

export function useApi(): ApiClient {
  const api = use(ApiContext);
  if (api === null) throw new Error("useApi needs an ApiContext provider");
  return api;
}

/** Poll delay for /api/app, 1 s until the first ingest has finished, then 10 s. */
export function appPollInterval(data: AppInfo | undefined): number {
  return data !== undefined && data.ingest.state !== "done" ? INGEST_POLL_MS : APP_POLL_MS;
}

/**
 * Server facts for one project. Hidden tabs stop polling, and a tab returning to view refetches
 * at once, because TanStack's focus manager listens to visibilitychange.
 */
export function useAppInfo(project: string | null): UseQueryResult<AppInfo> {
  const api = useApi();
  return useQuery({
    queryKey: ["app", project],
    queryFn: ({ signal }) => api.getApp(project, signal),
    refetchInterval: (query) => appPollInterval(query.state.data),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
    retry: false,
  });
}

/** The project list, at start and every 60 s. */
export function useProjects(): UseQueryResult<ProjectsAnswer> {
  const api = useApi();
  return useQuery({
    queryKey: ["projects"],
    queryFn: ({ signal }) => api.getProjects(signal),
    refetchInterval: PROJECTS_POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
    retry: false,
  });
}
