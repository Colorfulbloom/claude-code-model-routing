/*
 * Sample cells for the Reference pages' own components (M5). The layer names are the ones the
 * order ladder shows for the main session's effort level, from the en.ts deck.
 */
import { OrderLadder, type OrderLadderLayer } from "@/components/OrderLadder/OrderLadder";
import { t } from "@/strings/t";

export type OrderLadderState = "row" | "wrapped" | "vertical" | "single";

const LAYERS: readonly OrderLadderLayer[] = [
  { id: "env", label: t("ly_env") },
  { id: "flag", label: t("ly_flag") },
  { id: "managed", label: t("sc_managed") },
  { id: "cli", label: t("ly_cli") },
  { id: "local", label: t("sc_project_local") },
  { id: "project", label: t("sc_project") },
  { id: "user", label: t("sc_user") },
  { id: "default", label: t("ly_default") },
];

export function OrderLadderDemo({ state }: { state: OrderLadderState }) {
  switch (state) {
    case "row":
      return <OrderLadder layers={LAYERS.slice(0, 4)} />;
    case "wrapped":
      return (
        <div className="sheet-narrow">
          <OrderLadder layers={LAYERS} />
        </div>
      );
    case "vertical":
      return (
        <div className="sheet-narrow">
          <OrderLadder layers={LAYERS} vertical />
        </div>
      );
    case "single":
      return <OrderLadder layers={LAYERS.slice(-1)} />;
  }
}
