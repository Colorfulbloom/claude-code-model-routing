/*
 * The app root. The access gate decides what shows. Hold is a brand-only screen, locked and
 * stopped show their gate pages, and unlocked checks first run before it renders the router.
 */
import { useState, useSyncExternalStore } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { RouterProvider } from "react-router";
import { ApiContext, useAppInfo, useProjects } from "@/api/client";
import type { ApiClient } from "@/api/client";
import type { Ingest } from "@/api/types";
import type { Access } from "@/app/access";
import { StatusRegion } from "@/app/harness";
import { livePath } from "@/app/nav";
import { createAppRouter } from "@/app/router";
import { parseRoute } from "@/app/routes";
import { WaitHold } from "@/components/WaitHold/WaitHold";
import type { Launch } from "@/lib/launch";
import { FirstRunPage, LockedPage, StoppedPage } from "@/pages/GatePages";
import { t } from "@/strings/t";

interface AppProps {
  api: ApiClient;
  queryClient: QueryClient;
  launch: Launch;
}

/** The router. When first run just finished, it opens on the launch project's Live. */
function ReadyRouter({ access, goTo }: { access: Access; goTo: string | null }) {
  // Created here, so the router first reads the hash after the gate has opened.
  const [router] = useState(() => {
    if (goTo !== null) history.replaceState(null, "", `#${goTo}`);
    return createAppRouter(access);
  });
  return <RouterProvider router={router} />;
}

/**
 * A first ingest with a known total of zero files (an empty transcript folder) holds on the
 * brand-only page, so the "Counting files" view never flashes before the server answers done.
 * While totals are still unknown (null), first run shows, because the count is real work.
 */
function holdsFirstRun(ingest: Ingest): boolean {
  return ingest.state !== "done" && ingest.state !== "failed" && ingest.files_total === 0;
}

/**
 * Unlocked: reads /api/app and /api/projects first, so names and counts show on the first paint.
 * While the first ingest is not done it shows first run, and when it finishes it goes to Live.
 */
function Unlocked({ access, command }: { access: Access; command: string }) {
  const route = access.getRoute();
  const project = route === null ? null : (parseRoute(route)?.project ?? access.getProject());
  const app = useAppInfo(project ?? access.getProject());
  const projects = useProjects();
  const [sawFirstRun, setSawFirstRun] = useState(false);

  const info = app.data;
  const held = info !== undefined && holdsFirstRun(info.ingest);
  const firstRun = info !== undefined && info.ingest.state !== "done" && !held;
  if (firstRun && !sawFirstRun) setSawFirstRun(true);

  if (held) return <WaitHold brand={t("product")} />;
  if (firstRun) return <FirstRunPage info={info} command={command} />;
  if (app.isPending || projects.isPending) return <WaitHold brand={t("product")} />;
  return <ReadyRouter access={access} goTo={sawFirstRun ? livePath(access.getProject()) : null} />;
}

export function App({ api, queryClient, launch }: AppProps) {
  const { access } = api;
  const gate = useSyncExternalStore(access.subscribe, access.getState);
  const route = access.getRoute();

  return (
    <QueryClientProvider client={queryClient}>
      <ApiContext value={api}>
        <StatusRegion />
        {gate.kind === "hold" ? (
          <WaitHold brand={t("product")} status={t("hold_status")} />
        ) : gate.kind === "unlocked" ? (
          <Unlocked access={access} command={launch.command} />
        ) : gate.kind === "locked" ? (
          <LockedPage gate={gate} command={launch.command} route={route} />
        ) : (
          <StoppedPage command={launch.command} route={route} />
        )}
      </ApiContext>
    </QueryClientProvider>
  );
}
