/* Maps the server's project rows to the picker's items, with the words from the string deck. */
import type { ProjectItem } from "@/components/ProjectPicker/ProjectPicker";
import type { Project } from "@/api/types";
import { t } from "@/strings/t";

/** A project that is running shows "Agent working", otherwise its folder state in words. */
export function projectItem(project: Project): ProjectItem {
  const base = { id: project.key, name: project.name, path: project.display_path };
  if (project.state === "no_claude_folder") {
    return {
      ...base,
      kind: "idle",
      stateWord: t("pk_state_no_claude_folder"),
      detail: t("pk_st_noclaude_d"),
    };
  }
  if (project.state === "folder_not_found") {
    return {
      ...base,
      kind: "bad",
      stateWord: t("pk_state_folder_not_found"),
      detail: t("pk_st_notfound_d"),
    };
  }
  return project.running
    ? { ...base, kind: "working", stateWord: t("pk_running") }
    : { ...base, kind: "ready", stateWord: t("pk_state_ok") };
}
