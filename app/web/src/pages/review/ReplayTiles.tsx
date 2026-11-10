/* The four tiles of Session review, from the tile view that lib/replay-view.ts builds at the line. */
import { Ring } from "@/components/Ring/Ring";
import { RunDots } from "@/components/RunDots/RunDots";
import { Tile } from "@/components/Tile/Tile";
import type { ReplayTilesView } from "@/lib/replay-view";
import { t } from "@/strings/t";

export function ReplayTiles({ view }: { view: ReplayTilesView }) {
  return (
    <div className="tiles sreview-tiles" data-mode={view.mode}>
      <Tile
        label={view.cost.label}
        qualifier={view.cost.qualifier}
        value={view.cost.value}
        delta={view.cost.delta}
        {...(view.cost.note !== null ? { note: view.cost.note } : {})}
      />
      <Tile label={view.tokens.label} value={view.tokens.value} delta={view.tokens.delta} />
      <Tile
        label={view.cache.label}
        value={view.cache.value}
        delta={view.cache.delta}
        proof={<Ring percent={view.cache.percent} />}
      />
      <Tile
        label={view.runs.label}
        value={view.runs.value}
        delta={view.runs.delta}
        proof={<RunDots working={view.runs.working} finished={view.runs.finished} />}
      />
    </div>
  );
}

/** The tiles while the first answer is on its way. One line tells a screen reader. */
export function ReplayTilesLoading() {
  return (
    <div className="tiles sreview-tiles" aria-busy="true">
      <Tile label={t("rv_t_cost")} value="" delta="" loading={{ label: t("lv_loading") }} />
      <Tile label={t("t_tokens")} value="" delta="" loading={{ label: "" }} />
      <Tile label={t("t_cache")} value="" delta="" loading={{ label: "" }} />
      <Tile label={t("t_runs")} value="" delta="" loading={{ label: "" }} />
    </div>
  );
}
