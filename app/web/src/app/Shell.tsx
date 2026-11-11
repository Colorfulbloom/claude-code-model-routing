/*
 * The app shell. At 721px and up it is the sidebar with the main column beside it. At 720px and
 * below it is the sticky top bar, the main column and the fixed tab bar, which comes last in the
 * DOM. It renders one layout, never both, so the page keeps a single nav landmark.
 *
 * Data. /api/projects at shell start (names show on the first paint), /api/app for the project
 * in the route (the Working mark, the To fix count, the Claude Code version). While calls fail
 * the Working mark drops and a quiet "Updated {time}" line shows the last answer.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { RefObject } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { useApi, useAppInfo, usePrices, useProjects } from "@/api/client";
import { toFixNav } from "@/api/setup";
import { useActiveProject } from "@/app/active-project";
import { hidesTabBar, livePath, projectHref, sidebarCurrent, tabCurrent } from "@/app/nav";
import { pageName, parseRoute, routeForProject } from "@/app/routes";
import type { PageId } from "@/app/routes";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { NewTabLine } from "@/components/NewTabLine/NewTabLine";
import {
  projectOption,
  ProjectsEmpty,
  ProjectTray,
} from "@/components/ProjectPicker/ProjectPicker";
import { RunStateGlyph } from "@/components/RunStateGlyph/RunStateGlyph";
import { Select } from "@/components/Select/Select";
import { Sidebar } from "@/components/Sidebar/Sidebar";
import { SidebarFooter } from "@/components/SidebarFooter/SidebarFooter";
import { StoppedNotice } from "@/components/StoppedNotice/StoppedNotice";
import type { SidebarGroup } from "@/components/Sidebar/Sidebar";
import { TabBar } from "@/components/TabBar/TabBar";
import type { TabBarItem } from "@/components/TabBar/TabBar";
import { TopBar } from "@/components/TopBar/TopBar";
import { clockMedium } from "@/lib/clock";
import { footerLines } from "@/lib/history";
import { stoppedSentence } from "@/lib/stopped";
import { useIsDesktop } from "@/lib/media";
import { projectItem } from "@/lib/projects";
import { isSetupPart } from "@/lib/setup-routes";
import { PART_NAMES } from "@/lib/setup-words";
import { DEFAULT_RANGE, parseRange, readLastRange, reviewPath } from "@/lib/range";
import { t, tn } from "@/strings/t";

interface ShellProps {
  page: PageId;
  /** The project in the route, null on Reference and More. */
  routeProject: string | null;
  pathname: string;
  mainRef: RefObject<HTMLElement | null>;
  children: React.ReactNode;
}

const reviewLinks = [
  { id: "summary", rest: "/review/summary", label: () => t("nav_summary") },
  { id: "sessions", rest: "/review/sessions", label: () => t("nav_sessions") },
  { id: "agents", rest: "/review/agents", label: () => t("nav_agents") },
  { id: "models", rest: "/review/models", label: () => t("nav_models") },
] as const;

export function Shell({ page, routeProject, pathname, mainRef, children }: ShellProps) {
  const { access, connection } = useApi();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const desktop = useIsDesktop();
  const projects = useProjects();
  const projectList = projects.data?.projects;
  const activeProject = useActiveProject(routeProject, { fallback: page !== "picker" });
  // A setup item page is named by its part ("Instructions"), as the desktop h1 is.
  const surfacePart = page === "surface" ? parseRoute(pathname)?.part : undefined;
  const barTitle =
    surfacePart !== undefined && isSetupPart(surfacePart)
      ? PART_NAMES[surfacePart]()
      : pageName(page);
  const app = useAppInfo(activeProject);
  const prices = usePrices();
  const conn = useSyncExternalStore(connection.subscribe, connection.getState);
  const otherTab = useSyncExternalStore(access.subscribe, access.getOtherTabBack);

  const stopped = app.data?.history.pass_error ?? null;
  // The notice is a polite status only when it appears after a load that had none, so it speaks once.
  const [sawClear, setSawClear] = useState(false);
  if (app.data !== undefined && stopped === null && !sawClear) setSawClear(true);
  const announce = sawClear;

  const [trayOpen, setTrayOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!trayOpen && restoreFocus.current) {
      restoreFocus.current = false;
      triggerRef.current?.focus();
    }
  }, [trayOpen]);

  // The new-tab line stays until the person moves to another page.
  const shownAt = useRef<string | null>(null);
  useEffect(() => {
    if (otherTab === null) {
      shownAt.current = null;
    } else if (shownAt.current === null) {
      shownAt.current = pathname;
    } else if (shownAt.current !== pathname) {
      access.acknowledgeOtherTabBack();
    }
  }, [otherTab, pathname, access]);

  if (page === "more" && desktop) return <Navigate to={livePath(activeProject)} replace />;

  const items = (projectList ?? []).map(projectItem);
  const projectName = items.find((item) => item.id === activeProject)?.name ?? activeProject;
  // Anything but the owner's own data gets the quiet mark, so demo numbers never pass for real ones.
  const demoMark =
    app.data !== undefined && app.data.mode !== "real" ? (
      <HelpTerm help="shell.demo">{t("lv_demo")}</HelpTerm>
    ) : null;
  // Only an `ok` state shows a number. Unchecked and failed have their own accessible names and no
  // number. Before the first app answer the link is plain "To fix".
  const nav = toFixNav(app.data);
  const toFix = nav.count ?? 0;
  const toFixName =
    app.data === undefined
      ? undefined
      : nav.state === "unchecked"
        ? t("tofix_unchecked_aria")
        : nav.state === "failed"
          ? t("tofix_failed_aria")
          : toFix > 0
            ? tn("tofix_aria", toFix)
            : undefined;
  const toFixShowsCount = nav.state === "ok" && toFix > 0;
  const working =
    !conn.retrying && (app.data?.running.some((r) => r.project === activeProject) ?? false);

  function switchProject(key: string): void {
    access.setProject(key);
    const parsed = parseRoute(pathname);
    void navigate(
      parsed?.project == null ? livePath(key) : routeForProject(pathname, key, () => false),
    );
  }

  const pickerProps = {
    heading: t("pk_h"),
    items,
    value: activeProject,
    emptyTitle: t("pk_empty_h"),
    emptyBody: t("pk_empty"),
    loadingText: t("pk_loading"),
    loading: projectList === undefined,
  };

  const sidebarCurrentId = sidebarCurrent(page);
  // On a Review page the sidebar's Review links keep the range, as the phone's segmented pages do.
  const onReview =
    page === "summary" ||
    page === "sessions" ||
    page === "session" ||
    page === "agents" ||
    page === "models";
  const reviewRange = onReview
    ? parseRange(search.get("range"), readLastRange() ?? DEFAULT_RANGE).range
    : null;
  const groups: SidebarGroup[] = [
    {
      id: "live",
      items: [
        {
          id: "live",
          href: projectHref(activeProject, "/live"),
          label: t("nav_live"),
          icon: "live",
          current: sidebarCurrentId === "live",
          ...(working
            ? { end: <RunStateGlyph state="working">{t("nav_working")}</RunStateGlyph> }
            : {}),
        },
      ],
    },
    {
      id: "review",
      heading: t("nav_review"),
      items: reviewLinks.map(({ id, rest, label }) => ({
        id,
        href:
          reviewRange === null || activeProject === null
            ? projectHref(activeProject, rest)
            : `#${reviewPath(activeProject, id, reviewRange)}`,
        label: label(),
        icon: id,
        current: sidebarCurrentId === id,
      })),
    },
    {
      id: "setup",
      heading: t("nav_setup_h"),
      items: [
        {
          id: "setup",
          href: projectHref(activeProject, "/setup"),
          label: t("nav_setup"),
          icon: "setup",
          current: sidebarCurrentId === "setup",
        },
        {
          id: "tofix",
          href: projectHref(activeProject, "/to-fix"),
          label: t("nav_tofix"),
          icon: "tofix",
          current: sidebarCurrentId === "tofix",
          ...(toFixShowsCount ? { end: t("tofix_count", { n: toFix }) } : {}),
          ...(toFixName !== undefined ? { name: toFixName } : {}),
          help: <HelpButton help="shell.nav" />,
        },
      ],
    },
    {
      id: "reference",
      heading: t("nav_ref_h"),
      items: [
        {
          id: "decides",
          href: "#/reference/decides",
          label: t("nav_decides"),
          icon: "decides",
          current: sidebarCurrentId === "decides",
        },
        {
          id: "glossary",
          href: "#/reference/glossary",
          label: t("nav_glossary"),
          icon: "glossary",
          current: sidebarCurrentId === "glossary",
        },
      ],
    },
  ];

  const tabId = tabCurrent(page);
  const tabItems: TabBarItem[] = [
    {
      id: "live",
      href: projectHref(activeProject, "/live"),
      label: t("nav_live"),
      icon: "live",
      current: tabId === "live",
    },
    {
      id: "review",
      href: projectHref(activeProject, "/review/summary"),
      label: t("nav_review"),
      icon: "review",
      current: tabId === "review",
    },
    {
      id: "setup",
      href: projectHref(activeProject, "/setup"),
      label: t("nav_setup_h"),
      icon: "setup",
      current: tabId === "setup",
    },
    {
      id: "tofix",
      href: projectHref(activeProject, "/to-fix"),
      label: t("nav_tofix"),
      icon: "tofix",
      current: tabId === "tofix",
      ...(toFixShowsCount ? { count: t("tofix_count", { n: toFix }) } : {}),
      ...(toFixName !== undefined ? { name: toFixName } : {}),
    },
    { id: "more", href: "#/more", label: t("nav_more"), icon: "more", current: tabId === "more" },
  ];

  const backRoute = otherTab?.route == null ? null : parseRoute(otherTab.route);
  const backPage = backRoute?.page ?? page;
  const backProject = backRoute === null ? projectName : (backRoute.project ?? t("product"));

  return (
    <div className="shell" data-shell={desktop ? "desktop" : "phone"}>
      {desktop ? (
        <Sidebar
          label={t("nav_aria")}
          brand={t("product")}
          {...(demoMark !== null ? { badge: demoMark } : {})}
          groups={groups}
          {...(app.data !== undefined
            ? {
                footer: (
                  <SidebarFooter lines={footerLines(app.data, prices.data, app.data.server_time)} />
                ),
              }
            : {})}
          projectSlot={
            <Select
              stacked
              label={t("project_label")}
              items={items.map(projectOption)}
              value={activeProject}
              onChange={switchProject}
              placeholder={t("pk_placeholder")}
              heading={t("pk_h")}
              emptyState={
                projectList === undefined ? (
                  <p className="pk-note muted" role="status">
                    {t("pk_loading")}
                  </p>
                ) : (
                  <ProjectsEmpty title={t("pk_empty_h")} body={t("pk_empty")} />
                )
              }
            />
          }
        />
      ) : (
        <TopBar
          title={page === "picker" ? t("product") : barTitle}
          {...(demoMark !== null ? { badge: demoMark } : {})}
          {...(page === "picker" || (activeProject !== null && projectName !== null)
            ? {
                project: {
                  name: projectName ?? t("pk_placeholder"),
                  placeholder: projectName === null,
                  open: page === "picker" || trayOpen,
                  onPress: () => {
                    if (page !== "picker") setTrayOpen(true);
                  },
                },
                projectRef: triggerRef,
              }
            : {})}
        />
      )}
      <main className="shell-main" ref={mainRef}>
        <div className="shell-content">
          {otherTab !== null && (
            <NewTabLine>
              {t("lk_tab_back", { page: pageName(backPage), project: backProject ?? t("product") })}
            </NewTabLine>
          )}
          {stopped !== null && (
            <StoppedNotice {...(announce ? { role: "status" as const } : {})}>
              {stoppedSentence(stopped, app.data?.server_time ?? stopped.since)}
            </StoppedNotice>
          )}
          {conn.retrying && (
            <p className="shell-updated muted">
              {conn.lastAnswerAt === null
                ? t("updated_never")
                : t("updated_at", { time: clockMedium(conn.lastAnswerAt) })}{" "}
              <HelpButton help="shell.updated" />
            </p>
          )}
          {children}
        </div>
      </main>
      {!desktop && (
        <ProjectTray
          {...pickerProps}
          closeLabel={t("pk_close")}
          isOpen={trayOpen}
          onChange={(key) => {
            setTrayOpen(false);
            switchProject(key);
          }}
          onOpenChange={(open) => {
            if (!open) restoreFocus.current = true;
            setTrayOpen(open);
          }}
        />
      )}
      {!desktop && !hidesTabBar(page) && <TabBar label={t("nav_aria")} items={tabItems} />}
    </div>
  );
}
