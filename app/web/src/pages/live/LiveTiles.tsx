/* The four tiles under the header, from the tile view the mapping builds. */
import { Ring } from "@/components/Ring/Ring";
import { RunDots } from "@/components/RunDots/RunDots";
import { Spark } from "@/components/Spark/Spark";
import { Tile } from "@/components/Tile/Tile";
import type { TilesView } from "@/lib/live-tiles";
import { t } from "@/strings/t";

export function LiveTiles({ view }: { view: TilesView }) {
  return (
    <div className="tiles">
      <Tile
        label={view.cost.label}
        qualifier={view.cost.qualifier}
        value={view.cost.value}
        delta={view.cost.delta}
        {...(view.cost.note !== null ? { note: view.cost.note } : {})}
        proof={<Spark values={view.cost.spark} />}
      />
      <Tile label={t("t_tokens")} value={view.tokens.value} delta={view.tokens.delta} />
      <Tile
        label={t("t_cache")}
        value={view.cache.value}
        delta={view.cache.delta}
        proof={<Ring percent={view.cache.percent} />}
      />
      <Tile
        label={view.agents.label}
        value={view.agents.value}
        delta={view.agents.delta}
        proof={<RunDots working={view.agents.working} finished={view.agents.finished} />}
      />
    </div>
  );
}

/** The tiles while the first answer is on its way. One line tells a screen reader. */
export function LiveTilesLoading() {
  return (
    <div className="tiles" aria-busy="true">
      <Tile label={t("t_cost")} value="" delta="" loading={{ label: t("lv_loading") }} />
      <Tile label={t("t_tokens")} value="" delta="" loading={{ label: "" }} />
      <Tile label={t("t_cache")} value="" delta="" loading={{ label: "" }} />
      <Tile label={t("t_agents")} value="" delta="" loading={{ label: "" }} />
    </div>
  );
}
