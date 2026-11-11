/* The four Summary tiles: cost, sessions, tokens and the cache share, each compared as the range says. */
import type { Summary } from "@/api/types";
import { Tile } from "@/components/Tile/Tile";
import { tileHelpValues } from "@/lib/live-tiles";
import { buildSummaryTiles } from "@/lib/review-view";
import type { TileView } from "@/lib/review-view";
import type { HelpId } from "@/strings/help";
import { t } from "@/strings/t";
import { CardError } from "./CardStates";

/** One tile of the four, by its place in the list. Its "?" gets the numbers the tile shows. */
function SummaryTile({
  tiles,
  index,
  help,
}: {
  tiles: readonly TileView[];
  index: number;
  help: Extract<HelpId, `summary.${string}`>;
}) {
  const tile = tiles[index];
  if (tile === undefined) return null;
  return (
    <Tile
      label={tile.label}
      {...(tile.qualifier !== undefined ? { qualifier: tile.qualifier } : {})}
      value={tile.value}
      delta={tile.delta}
      {...(tile.note !== undefined ? { note: tile.note } : {})}
      help={{ id: help, values: tileHelpValues(tile) }}
    />
  );
}

export function SummaryTiles({ summary }: { summary: Summary }) {
  const tiles = buildSummaryTiles(summary);
  return (
    <div className="tiles">
      <SummaryTile tiles={tiles} index={0} help="summary.cost" />
      <SummaryTile tiles={tiles} index={1} help="summary.sessions" />
      <SummaryTile tiles={tiles} index={2} help="summary.tokens" />
      <SummaryTile tiles={tiles} index={3} help="summary.cache" />
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
