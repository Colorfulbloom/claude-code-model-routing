/*
 * The hash router. Every route from plan-a section 2 renders inside the shell, with the
 * placeholder page for its id, except Live, the Review pages, More and the picker, which have their own pages. The
 * picker is a modal over an empty shell.
 * RouteLayout runs the route harness: title, focus on the h1, polite status.
 */
import { useEffect, useRef } from "react";
import { Outlet, createHashRouter, redirect, useLocation, useMatches } from "react-router";
import type { RouteObject } from "react-router";
import { useApi, useProjects } from "@/api/client";
import type { Access } from "@/app/access";
import { useHarness } from "@/app/harness";
import { pageName } from "@/app/routes";
import type { PageId } from "@/app/routes";
import { Shell } from "@/app/Shell";
import { LivePage } from "@/pages/LivePage";
import { MorePage } from "@/pages/MorePage";
import { PickerPage } from "@/pages/PickerPage";
import type { RouteContext } from "@/pages/PickerPage";
import { Placeholder } from "@/pages/Placeholder";
import { AgentsPage } from "@/pages/review/AgentsPage";
import { ModelsPage } from "@/pages/review/ModelsPage";
import { SessionReviewPage } from "@/pages/review/SessionReviewPage";
import { SessionsPage } from "@/pages/review/SessionsPage";
import { SummaryPage } from "@/pages/review/SummaryPage";
import { SurfacePage } from "@/pages/setup/SurfacePage";
import { ToFixPage } from "@/pages/setup/ToFixPage";
import { YourSetupPage } from "@/pages/setup/YourSetupPage";
import { isSetupPart } from "@/lib/setup-routes";
import { PART_NAMES } from "@/lib/setup-words";
import { t } from "@/strings/t";

interface RouteHandle {
  page: PageId;
}

function isHandle(value: unknown): value is RouteHandle {
  return typeof value === "object" && value !== null && "page" in value;
}

function RouteLayout() {
  const { pathname, search } = useLocation();
  const matches = useMatches();
  const api = useApi();
  const last = matches.at(-1);
  const page: PageId = last !== undefined && isHandle(last.handle) ? last.handle.page : "picker";
  const project = matches.map((m) => m.params.project).find((p) => p !== undefined) ?? null;

  const projects = useProjects();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  // A surface page is named by its part, and picking an item is no route change for focus.
  const part = matches.map((m) => m.params.part).find((p) => p !== undefined) ?? null;
  const name =
    page === "surface" && part !== null && isSetupPart(part) ? PART_NAMES[part]() : pageName(page);
  const focusId = page === "surface" ? pathname.split("/").slice(0, 5).join("/") : pathname;
  const title =
    projectName === null
      ? t("title_bare", { page: name })
      : t("title_project", { page: name, project: projectName });

  // The picker's h1 is in its dialog, which sits outside the main column.
  const mainRef = useRef<HTMLElement>(null);
  const overlayRef = useRef<HTMLElement>(null);
  // Live names its session in the query, so a session switch is a route change for focus too.
  const session = page === "live" ? new URLSearchParams(search).get("session") : null;
  useHarness(page === "picker" ? overlayRef : mainRef, {
    id: session === null ? focusId : `${focusId}?session=${session}`,
    title,
    status: name,
  });

  useEffect(() => {
    api.access.saveRoute(`${pathname}${search}`);
  }, [api, pathname, search]);

  return (
    <Shell page={page} routeProject={project} pathname={pathname} mainRef={mainRef}>
      <Outlet context={{ overlayRef } satisfies RouteContext} />
    </Shell>
  );
}

function route(path: string, id: PageId): RouteObject {
  return {
    path,
    element:
      id === "more" ? (
        <MorePage />
      ) : id === "picker" ? (
        <PickerPage />
      ) : id === "live" ? (
        <LivePage />
      ) : id === "summary" ? (
        <SummaryPage />
      ) : id === "sessions" ? (
        <SessionsPage />
      ) : id === "session" ? (
        <SessionReviewPage />
      ) : id === "agents" ? (
        <AgentsPage />
      ) : id === "models" ? (
        <ModelsPage />
      ) : id === "setup" ? (
        <YourSetupPage />
      ) : id === "surface" ? (
        <SurfacePage />
      ) : id === "to_fix" ? (
        <ToFixPage />
      ) : (
        <Placeholder page={id} />
      ),
    handle: { page: id } satisfies RouteHandle,
  };
}

export function appRoutes(access: Access): RouteObject[] {
  return [
    {
      element: <RouteLayout />,
      children: [
        {
          ...route("/", "picker"),
          // The launch project's Live, or the picker when there is none.
          loader: () => {
            const project = access.getProject();
            return project === null ? null : redirect(`/p/${encodeURIComponent(project)}/live`);
          },
        },
        route("/p/:project/live", "live"),
        route("/p/:project/review/summary", "summary"),
        route("/p/:project/review/sessions", "sessions"),
        route("/p/:project/review/sessions/:id", "session"),
        route("/p/:project/review/agents", "agents"),
        route("/p/:project/review/agents/new", "agent_new"),
        route("/p/:project/review/agents/:name/edit", "agent_edit"),
        route("/p/:project/review/models", "models"),
        route("/p/:project/setup", "setup"),
        route("/p/:project/setup/:part", "surface"),
        route("/p/:project/setup/:part/:item", "surface"),
        route("/p/:project/setup/:part/:item/edit", "surface_edit"),
        route("/p/:project/to-fix", "to_fix"),
        route("/reference/decides", "decides"),
        route("/reference/glossary", "glossary"),
        route("/more", "more"),
        // Unknown routes land on the picker rather than a blank page.
        { path: "*", loader: () => redirect("/") },
      ],
    },
  ];
}

/** Creates the hash router. Call it after access.start(), so the code is already out of the hash. */
export function createAppRouter(access: Access) {
  return createHashRouter(appRoutes(access));
}
