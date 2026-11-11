/*
 * Words the edit components share (M6a): the scope names, the outcome of a scope in the Save to
 * list, and a helper that sets a code span inside a sentence that holds one placeholder. Every call
 * is a literal t() so the static key test sees it (fact K-819f).
 */
import type { EditScope, ScopeOutcome } from "@/api/edit";
import type { SettingStatus } from "@/components/StatusChip/StatusChip";
import { STATUS_WORDS } from "@/lib/model-check";
import { t } from "@/strings/t";

/** The scope as the person reads it, such as "Project local". */
export function scopeName(scope: EditScope): string {
  switch (scope) {
    case "local":
      return t("sc_project_local");
    case "project":
      return t("sc_project");
    case "user":
      return t("sc_user");
  }
}

/** What the scope means in plain words, such as "Just you, this project". */
export function scopeMeaning(scope: EditScope): string {
  switch (scope) {
    case "local":
      return t("sc_project_local_2");
    case "project":
      return t("sc_project_2");
    case "user":
      return t("sc_user_2");
  }
}

/** A scope code from a server `params` value, or null when the value is some other word. */
export function asScope(value: string | undefined): EditScope | null {
  return value === "local" || value === "project" || value === "user" ? value : null;
}

export interface OutcomeView {
  status: SettingStatus;
  word: string;
}

/**
 * The outcome of saving to a scope. In effect reads "Takes effect" and overridden names the scope
 * that wins. The other statuses keep their own word, so a glyph is never the only signal.
 */
export function outcomeView(outcome: ScopeOutcome): OutcomeView {
  if (outcome.status === "in_effect") return { status: "in_effect", word: t("ed_takes_effect") };
  if (outcome.status === "overridden" && outcome.beaten_by !== null) {
    return {
      status: "overridden",
      word: t("ed_overridden_by", { scope: scopeName(outcome.beaten_by) }),
    };
  }
  return { status: outcome.status, word: STATUS_WORDS[outcome.status] };
}

/** The word for a status, from the seven the whole app shares. */
export function statusWord(status: SettingStatus): string {
  return STATUS_WORDS[status];
}

/**
 * Splits a sentence on the one place a code span goes. Pass the sentence made with a marker as the
 * placeholder's value, and the marker. The caller sets the code element between the two parts.
 */
export const CODE_MARK = "\u0000";

export function splitOnMark(sentence: string): [string, string] {
  const at = sentence.indexOf(CODE_MARK);
  if (at < 0) return [sentence, ""];
  return [sentence.slice(0, at), sentence.slice(at + 1)];
}

/**
 * The full path of a file, with "~" for the home folder where the server gave one. The server
 * shows a file under the project relative to it (".claude/settings.local.json"), so this puts the
 * project's own path in front, the path the project list already carries. A path that is already
 * full ("~/..." or "/...") stays as it is, and so does a relative one when the project's path is
 * only a name, because a guess would name the wrong file.
 */
export function fullPathOf(path: string, projectPath: string | undefined): string {
  const full = (text: string): boolean => text.startsWith("~") || text.startsWith("/");
  if (full(path) || projectPath === undefined || !full(projectPath)) return path;
  return `${projectPath.replace(/\/+$/, "")}/${path}`;
}

/** The folder and the file name of a display path, so the name can be set in bold. */
export function splitPath(path: string): { dir: string; name: string } {
  const at = path.lastIndexOf("/");
  return at < 0
    ? { dir: "", name: path }
    : { dir: path.slice(0, at + 1), name: path.slice(at + 1) };
}
