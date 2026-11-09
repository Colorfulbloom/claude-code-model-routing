/*
 * The project picker on #/ when the launcher passed no project. The shell renders behind it with
 * an empty main column, and the picker is a modal over a scrim: a centred sheet at 721px and up,
 * the bottom tray at 720px and below. Its heading is the page h1, so the route harness points at
 * the dialog. Esc and the scrim go back to the previous in-app page, and do nothing when there is
 * none. Picking a project goes to its Live.
 */
import type { RefObject } from "react";
import { useLocation, useNavigate, useOutletContext } from "react-router";
import { useApi, useProjects } from "@/api/client";
import { livePath } from "@/app/nav";
import { ProjectTray } from "@/components/ProjectPicker/ProjectPicker";
import { useIsDesktop } from "@/lib/media";
import { projectItem } from "@/lib/projects";
import { t } from "@/strings/t";

/** What RouteLayout hands to its routes through the outlet. */
export interface RouteContext {
  /** Points at the picker dialog, so the route harness can focus its h1. */
  overlayRef: RefObject<HTMLElement | null>;
}

export function PickerPage() {
  const { access } = useApi();
  const navigate = useNavigate();
  const desktop = useIsDesktop();
  const projects = useProjects();
  const { overlayRef } = useOutletContext<RouteContext>();
  // The first location of a session has the key "default", so there is nothing to go back to.
  const canGoBack = useLocation().key !== "default";
  return (
    <ProjectTray
      layout={desktop ? "sheet" : "tray"}
      isOpen
      dismissable={canGoBack}
      focusOnMount={false}
      dialogRef={overlayRef}
      onOpenChange={(open) => {
        if (!open && canGoBack) void navigate(-1);
      }}
      headingLevel={1}
      heading={t("pk_h")}
      {...(canGoBack ? { closeLabel: t("pk_close") } : {})}
      items={(projects.data?.projects ?? []).map(projectItem)}
      value={null}
      onChange={(key) => {
        access.setProject(key);
        void navigate(livePath(key));
      }}
      emptyTitle={t("pk_empty_h")}
      emptyBody={t("pk_empty")}
      loadingText={t("pk_loading")}
      loading={projects.data === undefined}
    />
  );
}
