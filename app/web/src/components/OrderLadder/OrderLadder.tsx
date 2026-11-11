import { cx } from "../cx";
import "./OrderLadder.css";

export const states = ["row", "wrapped", "vertical", "single"] as const;

export interface OrderLadderLayer {
  /** Stable key, such as the layer's code. */
  id: string;
  /** The layer's name as the reader sees it, such as "Project local". */
  label: string;
}

export interface OrderLadderProps {
  /** The layers, highest first. The top one wins. */
  layers: readonly OrderLadderLayer[];
  /** The id of the heading that names the list, such as "Where Claude Code looks, top wins". */
  labelledBy?: string;
  /** The sheet only. Draws the phone layout, the vertical well, at any width. */
  vertical?: boolean;
  className?: string;
}

/**
 * The places Claude Code looks, in order. An ordered list of pills, each with its place number,
 * joined by a › that is drawn by CSS and never read. At 721px and up the pills run in a row and
 * wrap. At 720px and under the list becomes a vertical well, one layer to a line, because a wrapped
 * row of long names reads badly on a phone. The list is an ol, so a screen reader says the place
 * ("3 of 8") and the number on screen only repeats it.
 */
export function OrderLadder({ layers, labelledBy, vertical = false, className }: OrderLadderProps) {
  return (
    <ol
      className={cx("order-ladder", vertical && "is-vertical", className)}
      {...(labelledBy === undefined ? {} : { "aria-labelledby": labelledBy })}
    >
      {layers.map((layer, index) => (
        <li key={layer.id} className="order-ladder-layer">
          <span className="order-ladder-n num" aria-hidden="true">
            {index + 1}
          </span>
          <span className="order-ladder-name">{layer.label}</span>
        </li>
      ))}
    </ol>
  );
}
