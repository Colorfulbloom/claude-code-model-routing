/*
 * Whether this page can edit, and if not, which sentence says why (plan 5.2). Three facts decide it:
 * the server's edit mode (/api/app `edits.state`), the project's `edit_block` (/api/projects) and
 * the launch command (the `bartab-command` meta tag). The command in the reason line is always
 * that tag plus --allow-edits, never a string baked into the page.
 */
import { useMemo } from "react";
import { useAppInfo, useProjects } from "@/api/client";
import { readLaunch } from "@/lib/launch";

export type EditAvailability =
  /** /api/app hasn't answered yet, so the page says nothing about editing. */
  | { kind: "loading" }
  | { kind: "on" }
  /** Edits are off for this server. `command` turns them on. */
  | { kind: "off"; command: string }
  /** A demo or fixture run whose folders sit inside the Bar Tab checkout. */
  | { kind: "demo" }
  /** The project's folder is missing, so nothing in it can be edited. `path` is the folder as listed. */
  | { kind: "folder"; path: string };

const FLAG = "--allow-edits";

/** The command that starts Bar Tab with edits on: the launch command plus --allow-edits. */
export function commandWithEdits(command: string): string {
  return command.includes(FLAG) ? command : `${command} ${FLAG}`;
}

/** The command in the restart box, from the launch meta tag. It is read when the box shows. */
export function editCommand(): string {
  return commandWithEdits(readLaunch().command);
}

/**
 * The edit availability of one project. A missing folder is the only project-level block, and it
 * comes first, because turning edits on would not help it.
 */
export function useEditAvailability(project: string): EditAvailability {
  const app = useAppInfo(project);
  const projects = useProjects();
  const command = useMemo(() => commandWithEdits(readLaunch().command), []);
  const state = app.data?.edits.state;
  const entry = projects.data?.projects.find((p) => p.key === project);
  const block = entry?.edit_block ?? null;
  if (state === undefined) return { kind: "loading" };
  if (block === "folder_not_found") return { kind: "folder", path: entry?.display_path ?? project };
  switch (state) {
    case "on":
      return { kind: "on" };
    case "off":
      return { kind: "off", command };
    case "unavailable":
      return { kind: "demo" };
  }
}

/** The file name at the end of a display path, for the sentences that name the file. */
export function fileNameOf(path: string): string {
  const at = path.lastIndexOf("/");
  return at < 0 ? path : path.slice(at + 1);
}
