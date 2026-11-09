/*
 * The gate pages: locked, server stopped and first run, on GatePage (components.md entry 35).
 * The *Content parts are plain and take props, so the component sheet shows the same markup the
 * real pages use. The *Page parts add the route harness (title, focus on the h1, polite status).
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useApi } from "@/api/client";
import type { Ingest, AppInfo } from "@/api/types";
import type { GateState, LockReason } from "@/app/access";
import { useHarness } from "@/app/harness";
import { pageName, parseRoute } from "@/app/routes";
import { CommandRow } from "@/components/CommandRow/CommandRow";
import { GatePage } from "@/components/GatePage/GatePage";
import { NewTabLine } from "@/components/NewTabLine/NewTabLine";
import { ProgressSteps } from "@/components/ProgressSteps/ProgressSteps";
import type { ProgressStep } from "@/components/ProgressSteps/ProgressSteps";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { RetryRow } from "@/components/RetryRow/RetryRow";
import { clockShort } from "@/lib/clock";
import { t } from "@/strings/t";

export const STOPPED_RETRY_MS = 10_000;

/** "Agents, builder" for a kept route. The locked page has no read key, so it shows the project slug. */
function routeWords(route: string | null): { page: string; project: string } | null {
  if (route === null) return null;
  const parsed = parseRoute(route);
  if (parsed === null) return null;
  return { page: pageName(parsed.page), project: parsed.project ?? t("product") };
}

export function lockedBody(reason: LockReason): string {
  switch (reason) {
    case "no_key":
      return t("lk_body_no_key");
    case "code_used":
      return t("lk_body_code_used");
    case "code_expired":
      return t("lk_body_code_expired");
    case "code_unknown":
      return t("lk_body_code_unknown");
    case "server_restarted":
      return t("lk_body_server_restarted");
    case "wrong_project_key":
      return t("lk_body_wrong_project_key");
  }
}

function LockIcon() {
  return (
    <svg
      className="gate-icon"
      viewBox="0 0 12 14"
      width="22"
      height="26"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor" />
      <path
        d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

/* Locked */

export interface LockedContentProps {
  reason: LockReason;
  command: string;
  /** The route the tab was asked for, such as /p/builder/review/agents. */
  route: string | null;
}

export function LockedContent({ reason, command, route }: LockedContentProps) {
  const words = routeWords(route);
  return (
    <>
      <LockIcon />
      <h1 className="gate-title" data-gate="locked" data-reason={reason}>
        {t("lk_h")}
      </h1>
      <p>{lockedBody(reason)}</p>
      <CommandRow primary command={command} copyLabel={t("lk_copy")} copiedLabel={t("cs_copied")} />
      {words !== null && (
        <p className="gate-line">
          <span className="gate-line-mark" aria-hidden="true">
            {"↻"}
          </span>
          <span>{t("lk_route2", words)}</span>
        </p>
      )}
    </>
  );
}

export interface LockedPageProps {
  gate: Extract<GateState, { kind: "locked" }>;
  command: string;
  route: string | null;
}

export function LockedPage({ gate, command, route }: LockedPageProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  useHarness(rootRef, {
    id: `locked.${gate.reason}`,
    title: t("title_locked"),
    status: t("status_locked"),
  });
  const words = routeWords(route);
  return (
    <GatePage
      brand={t("product")}
      ref={rootRef}
      {...(gate.otherTabBack && words !== null
        ? { notice: <NewTabLine>{t("lk_tab_back", words)}</NewTabLine> }
        : {})}
    >
      <LockedContent reason={gate.reason} command={command} route={route} />
    </GatePage>
  );
}

/* Server stopped */

export interface StoppedContentProps {
  command: string;
  route: string | null;
  /** Epoch milliseconds of the last answer, null when there has been none. */
  lastAnswerAt: number | null;
  busy: boolean;
  onTryNow: () => void;
}

export function StoppedContent({
  command,
  route,
  lastAnswerAt,
  busy,
  onTryNow,
}: StoppedContentProps) {
  const words = routeWords(route);
  return (
    <>
      <h1 className="gate-title" data-gate="stopped" data-busy={busy ? "true" : "false"}>
        {t("stopped_h")}
      </h1>
      <p>{t("stopped_body")}</p>
      <CommandRow command={command} copyLabel={t("lk_copy")} copiedLabel={t("cs_copied")} />
      {words !== null && <p className="gate-line">{t("st_route", words)}</p>}
      <RetryRow
        retryText={t("st_retry")}
        lastText={
          lastAnswerAt === null
            ? t("updated_never")
            : t("st_last", { time: clockShort(lastAnswerAt) })
        }
        tryLabel={t("stopped_try_now")}
        busyLabel={t("st_trying")}
        busy={busy}
        onTryNow={onTryNow}
      />
    </>
  );
}

export interface StoppedPageProps {
  command: string;
  route: string | null;
}

/**
 * The server stopped page. It checks again every 10 seconds while the tab is visible, and Try now
 * checks at once. Both count as a request, so the button reads "Checking" while one runs. An
 * answer with the same instance resumes the tab, and a new instance moves it to the locked page.
 */
export function StoppedPage({ command, route }: StoppedPageProps) {
  const api = useApi();
  const conn = useSyncExternalStore(api.connection.subscribe, api.connection.getState);
  const [busy, setBusy] = useState(false);
  const project = (route === null ? null : parseRoute(route)?.project) ?? api.access.getProject();

  function check(): void {
    setBusy(true);
    api
      .getApp(project)
      .catch(() => {
        /* the client counts the failure and the page stays stopped */
      })
      .finally(() => {
        setBusy(false);
      });
  }

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      setBusy(true);
      api
        .getApp(project)
        .catch(() => {
          /* counted by the client */
        })
        .finally(() => {
          setBusy(false);
        });
    }, STOPPED_RETRY_MS);
    return () => {
      clearInterval(timer);
    };
  }, [api, project]);

  const rootRef = useRef<HTMLDivElement>(null);
  useHarness(rootRef, { id: "stopped", title: t("title_stopped"), status: t("status_stopped") });
  return (
    <GatePage brand={t("product")} ref={rootRef}>
      <StoppedContent
        command={command}
        route={route}
        lastAnswerAt={conn.lastAnswerAt}
        busy={busy}
        onTryNow={check}
      />
    </GatePage>
  );
}

/* First run */

export interface FirstRunContentProps {
  ingest: Ingest;
  command: string;
  /** The clock time the current retry started, shown while ingest.retrying is true. */
  retryingSince: string | null;
}

function count(n: number): string {
  return n.toLocaleString("en-US");
}

/** Fills {file} with a code element, so the path reads in mono. A missing file leaves the gap out. */
function reasonLine(ingest: Ingest): React.ReactNode {
  const error = ingest.error;
  if (error === null) return null;
  const marker = "\u0000";
  const text = (() => {
    switch (error.code) {
      case "config_dir_missing":
        return t("fr_fail_config_dir_missing");
      case "config_dir_unreadable":
        return t("fr_fail_config_dir_unreadable", { file: marker });
      case "store_unwritable":
        return t("fr_fail_store_unwritable", { file: marker });
      case "store_damaged":
        return t("fr_fail_store_damaged", { file: marker });
      case "unexpected":
        return t("fr_fail_unexpected", { file: marker });
    }
  })();
  const [before = "", after = ""] = text.split(marker);
  if (!text.includes(marker)) return text;
  return (
    <>
      {before}
      {error.file !== null && <code className="gate-file">{error.file}</code>}
      {after}
    </>
  );
}

export function FirstRunContent({ ingest, command, retryingSince }: FirstRunContentProps) {
  const failed = ingest.state === "failed";
  const retrying = !failed && ingest.retrying && retryingSince !== null;
  const done: Pick<ProgressStep, "state" | "stateWord"> = {
    state: "done",
    stateWord: t("fr_done"),
  };
  const files = t("fr_files", { n: count(ingest.files_done), m: count(ingest.files_total) });
  const percent =
    ingest.files_total > 0 ? Math.round((ingest.files_done / ingest.files_total) * 100) : 0;
  const third: ProgressStep = failed
    ? { id: "3", name: t("fr_s3"), state: "failed", stateWord: t("fr_failed"), note: files }
    : retrying
      ? {
          id: "3",
          name: t("fr_s3"),
          state: "current",
          stateWord: t("fr_now"),
          progress: { percent: 0, text: t("fr_retrying", { time: retryingSince }), live: true },
        }
      : {
          id: "3",
          name: t("fr_s3"),
          state: "current",
          stateWord: t("fr_now"),
          progress: { percent, text: files },
        };
  const steps: ProgressStep[] = [
    { id: "1", name: t("fr_s1"), ...done },
    { id: "2", name: t("fr_s2"), ...done },
    third,
  ];
  return (
    <>
      <h1
        className="gate-title"
        data-gate="firstrun"
        data-step-state={failed ? "failed" : retrying ? "retrying" : "running"}
      >
        {t("fr_h")}
      </h1>
      <p>{t("fr_body")}</p>
      <ProgressSteps label={t("fr_h")} steps={steps} />
      {failed ? (
        <RaisedFinding variant="error" title={t("fr_fail_h")}>
          <p>{reasonLine(ingest)}</p>
          <p>{t("fr_fail_fix")}</p>
          <CommandRow command={command} copyLabel={t("lk_copy")} copiedLabel={t("cs_copied")} />
        </RaisedFinding>
      ) : (
        <p className="muted gate-note">{t("fr_local")}</p>
      )}
    </>
  );
}

export function FirstRunPage({ info, command }: { info: AppInfo; command: string }) {
  const rootRef = useRef<HTMLDivElement>(null);
  useHarness(rootRef, {
    id: "first-run",
    title: t("title_bare", { page: t("fr_h") }),
    status: t("fr_h"),
  });
  // The retry line shows when this retry began, the first answer that said so.
  const [since, setSince] = useState<string | null>(null);
  const retrying = info.ingest.retrying;
  if (retrying && since === null) setSince(clockShort(info.server_time));
  if (!retrying && since !== null) setSince(null);
  return (
    <GatePage brand={t("product")} ref={rootRef}>
      <FirstRunContent ingest={info.ingest} command={command} retryingSince={since} />
    </GatePage>
  );
}
