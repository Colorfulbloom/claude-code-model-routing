/* The four Summary tiles: cost, sessions, tokens and the cache share, each compared as the range says. */
import type { Summary } from "@/api/types";
import { Tile } from "@/components/Tile/Tile";
import { buildSummaryTiles } from "@/lib/review-view";
import { t } from "@/strings/t";
import { CardError } from "./CardStates";

export function SummaryTiles({ summary }: { summary: Summary }) {
  return (
    <div className="tiles">
      {buildSummaryTiles(summary).map((tile) => (
        <Tile
          key={tile.label}
          label={tile.label}
          {...(tile.qualifier !== undefined ? { qualifier: tile.qualifier } : {})}
          value={tile.value}
          delta={tile.delta}
          {...(tile.note !== undefined ? { note: tile.note } : {})}
        />
      ))}
    </div>
  );
}

/** Bones at the tiles' height. The first tile carries the one spoken line. */
export function SummaryTilesLoading() {
  const card = t("nav_summary").toLowerCase();
  const line = t("ld_line", { card });
  return (
    <div className="tiles" aria-busy="true">
      <Tile
        label={t("rv_t_cost")}
        qualifier={t("t_cost_kx")}
        value=""
        delta=""
        loading={{ label: line }}
      />
      <Tile label={t("rv_t_sessions")} value="" delta="" loading={{ label: "" }} />
      <Tile label={t("rv_t_tokens")} value="" delta="" loading={{ label: "" }} />
      <Tile label={t("rv_t_cache")} value="" delta="" loading={{ label: "" }} />
    </div>
  );
}

export function SummaryTilesError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="review-tiles-error">
      <CardError card={t("nav_summary")} onRetry={onRetry} />
    </div>
  );
}
