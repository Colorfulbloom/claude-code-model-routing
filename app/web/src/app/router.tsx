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
import { takeReturnFocus, triggerSelector } from "@/components/HelpEntry/origin";
import { LivePage } from "@/pages/LivePage";
import { MorePage } from "@/pages/MorePage";
import { PickerPage } from "@/pages/PickerPage";
import type { RouteContext } from "@/pages/PickerPage";
import { Placeholder } from "@/pages/Placeholder";
import { DecidesPage } from "@/pages/reference/DecidesPage";
import { GlossaryPage } from "@/pages/reference/GlossaryPage";
import { AgentsPage } from "@/pages/review/AgentsPage";
import { ModelsPage } from "@/pages/review/ModelsPage";
import { SessionReviewPage } from "@/pages/review/SessionReviewPage";
import { SessionsPage } from "@/pages/review/SessionsPage";
import { SummaryPage } from "@/pages/review/SummaryPage";
import { ChangesPage } from "@/pages/setup/ChangesPage";
import { SurfacePage } from "@/pages/setup/SurfacePage";
import { ToFixPage } from "@/pages/setup/ToFixPage";
import { YourSetupPage } from "@/pages/setup/YourSetupPage";
import { isSetupPart, setupEditPath, setupPartPath } from "@/lib/setup-routes";
import { PART_NAMES } from "@/lib/setup-words";
import { t } from "@/strings/t";

/** How long Back to {page} waits for the "?" it names to appear on a page that is still loading. */
const RETURN_FOCUS_WAIT_MS = 4000;

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
  const onSurface = page === "surface" || page === "surface_edit";
  const name =
    onSurface && part !== null && isSetupPart(part) ? PART_NAMES[part]() : pageName(page);
  // The Reference pages move focus to their own target (a setting, a rule or a term), so a change of
  // target is no route change for focus, as picking an item on a surface page is none.
  const focusId = onSurface
    ? pathname.split("/").slice(0, 5).join("/")
    : page === "decides" || page === "glossary"
      ? pathname.split("/").slice(0, 3).join("/")
      : pathname;
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

  // Back to {page} from the Glossary names the "?" that opened it. Once the page is up, focus goes
  // back to that trigger. The page may still be loading, so the wait is a few seconds at most, and
  // a trigger that never comes leaves focus on the h1 the harness set.
  useEffect(() => {
    const help = takeReturnFocus(pathname);
    const main = mainRef.current;
    if (help === null || main === null) return undefined;
    const selector = triggerSelector(help);
    const focusIt = (): boolean => {
      const el = main.querySelector<HTMLElement>(selector);
      if (el === null) return false;
      el.focus();
      return document.activeElement === el;
    };
    if (focusIt()) return undefined;
    const watch = new MutationObserver(() => {
      if (focusIt()) watch.disconnect();
    });
    watch.observe(main, { childList: true, subtree: true });
    const stop = setTimeout(() => {
      watch.disconnect();
    }, RETURN_FOCUS_WAIT_MS);
    return () => {
      watch.disconnect();
      clearTimeout(stop);
    };
  }, [pathname, mainRef]);

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
      ) : id === "surface" || id === "surface_edit" ? (
        <SurfacePage />
      ) : id === "changes" ? (
        <ChangesPage />
      ) : id === "to_fix" ? (
        <ToFixPage />
      ) : id === "decides" ? (
        <DecidesPage />
      ) : id === "glossary" ? (
        <GlossaryPage />
      ) : (
        <Placeholder page={id} />
      ),
    handle: { page: id } satisfies RouteHandle,
  };
}

/**
 * A route that leaves for Your setup > Agents, with the agent selected when the URL names one.
 * The edit URL lands on the agent's edit route there, where the inspector says in a note that
 * M6a edits no agents. Review > Agents is not the landing page, because the note belongs to the
 * agent's file, not to its runs.
 */
function agentRedirect(path: string, id: PageId): RouteObject {
  return {
    path,
    loader: ({ params }) => {
      const project = params.project ?? "";
      const agent = params.name;
      return redirect(
        agent === undefined
          ? setupPartPath(project, "agents")
          : setupEditPath(project, "agents", agent),
      );
    },
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
        // M6a has no agent editing, so both agent routes leave for Your setup > Agents at route
        // level (a loader redirect, so no page renders first). The edit URL names the agent, so
        // that page opens it, with a note that takes focus.
        agentRedirect("/p/:project/review/agents/new", "agent_new"),
        agentRedirect("/p/:project/review/agents/:name/edit", "agent_edit"),
        route("/p/:project/review/models", "models"),
        route("/p/:project/setup", "setup"),
        route("/p/:project/setup/changes", "changes"),
        route("/p/:project/setup/:part", "surface"),
        route("/p/:project/setup/:part/:item", "surface"),
        route("/p/:project/setup/:part/:item/edit", "surface_edit"),
        route("/p/:project/to-fix", "to_fix"),
        // One route each, so a change of setting, rule or term never remounts the page. The page
        // reads the segments itself (parseRoute), and any other depth lands on the picker.
        route("/reference/decides/*", "decides"),
        route("/reference/glossary/*", "glossary"),
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
