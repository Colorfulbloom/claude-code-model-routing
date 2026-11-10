import { cx } from "../cx";
import { ModelSwatch, type Model } from "../ModelSwatch/ModelSwatch";
import "./ShareBar.css";

export const states = ["list", "table", "empty", "unpriced", "table-unpriced"] as const;

interface ShareBarBase {
  /** The model whose colour fills the bar. Without one the fill is neutral and no swatch shows. */
  model: Model | null;
  /**
   * This row's share of the total, 0 to 1. `null` means the share can't be known (a model with no
   * price): the track draws no fill and no edge, and `value` carries the caller's words.
   */
  share: number | null;
  /** The row's value as words, such as "$1.84". With a null share it is the caller's text, such as "No price". */
  value: string;
  /** The share as words, such as "42%". Leave it out when `share` is null, so 0% never shows. */
  percent?: string;
  className?: string;
}

export type ShareBarProps = ShareBarBase &
  (
    | {
        /** List: a 12 px track in a well, with the name and swatch. The caller wraps rows in a `ul`. */
        variant?: "list";
        /** The row's name. A page may add a second muted line, such as the model's name. */
        name: React.ReactNode;
      }
    | {
        /** Table: an 8 px track inside a cell. The row header already names the row. */
        variant: "table";
        name?: undefined;
      }
  );

/**
 * Shows each row's share of a total (components.md entry 19). The bar is hidden from assistive tech,
 * because the value and percent are text. A list row is an `li`, so the caller supplies the `ul`.
 * The 2 px start edge keeps a small share visible. Every word comes in through props.
 */
export function ShareBar(props: ShareBarProps) {
  const { model, share, value, percent, className } = props;
  const variant = props.variant ?? "list";
  const fraction =
    share !== null && Number.isFinite(share) ? Math.min(1, Math.max(0, share)) : null;
  const known = fraction !== null;
  const track = (
    <span className="share-bar-track" aria-hidden="true">
      {fraction !== null && (
        <span
          className={cx("share-bar-fill", model !== null && `share-bar-fill-${model}`)}
          style={{ width: `${String(fraction * 100)}%` }}
        />
      )}
    </span>
  );
  const figures = (
    <>
      <span className={cx("share-bar-value", "num", !known && "share-bar-value-wide")}>
        {value}
      </span>
      {known && percent !== undefined && <span className="share-bar-percent num">{percent}</span>}
    </>
  );
  if (variant === "table") {
    return (
      <div className={cx("share-bar", "share-bar-table", className)}>
        {track}
        {figures}
      </div>
    );
  }
  return (
    <li className={cx("share-bar", "share-bar-list", className)}>
      <span className="share-bar-name">
        {model !== null && <ModelSwatch model={model} />}
        {props.name}
      </span>
      {track}
      {figures}
    </li>
  );
}
