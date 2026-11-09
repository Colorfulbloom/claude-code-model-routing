/* The name a run shows on screen. The first run of an agent type shows the bare type. */
import { t } from "@/strings/t";

export interface Nameable {
  agent: string | null;
  label_n: number | null;
}

/** "Main session" for the main row, the bare type for number 1, "{type} {n}" from 2. */
export function runLabel(run: Nameable): string {
  if (run.agent === null) return t("tl_main");
  const n = run.label_n ?? 1;
  return n > 1 ? `${run.agent} ${String(n)}` : run.agent;
}
