/*
 * The one sentence of the updates-stopped notice, per whole-pass error code. The file path sits in
 * a code element so it reads in mono and wraps in a narrow column.
 */
import type { PassError } from "@/api/types";
import { clockStamp } from "@/lib/clock";
import { t } from "@/strings/t";

const MARK_T = "\u0001";
const MARK_F = "\u0002";

function template(code: PassError["code"]): string {
  switch (code) {
    case "config_dir_missing":
      return t("nt_stopped_config_dir_missing", { t: MARK_T });
    case "config_dir_unreadable":
      return t("nt_stopped_config_dir_unreadable", { t: MARK_T, f: MARK_F });
    case "store_unwritable":
      return t("nt_stopped_store_unwritable", { t: MARK_T, f: MARK_F });
    case "store_damaged":
      return t("nt_stopped_store_damaged", { t: MARK_T, f: MARK_F });
    case "store_newer":
      return t("nt_stopped_store_newer", { t: MARK_T });
    case "unexpected":
      return t("nt_stopped_unexpected", { t: MARK_T, f: MARK_F });
  }
}

/** The sentence for a pass error. `now` is the server's clock, which decides whether the time shows a date. */
export function stoppedSentence(error: PassError, now: number | string | Date): React.ReactNode {
  const text = template(error.code).replace(MARK_T, clockStamp(error.since, now));
  if (!text.includes(MARK_F)) return text;
  const [before = "", after = ""] = text.split(MARK_F);
  return (
    <>
      {before}
      {error.file !== null ? <code className="mono">{error.file}</code> : t("nt_stopped_nofile")}
      {after}
    </>
  );
}
