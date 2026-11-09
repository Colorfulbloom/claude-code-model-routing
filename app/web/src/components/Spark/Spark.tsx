import { cx } from "../cx";
import "./Spark.css";

export const states = ["bars", "unpriced", "dense"] as const;

/** Above this many bars the gaps go, so the bars stay readable in 96 px. */
export const DENSE_ABOVE = 32;

export interface SparkProps {
  /** One value per bucket, oldest first. `null` is a bucket with no price, drawn as a dashed stub. */
  values: readonly (number | null)[];
  className?: string;
}

/** The drawing is 96 units wide, the width the CSS gives it, so one unit is one px. */
const WIDTH = 96;
/** Bars sit 2 px apart, as the board's flex gap does. Past DENSE_ABOVE they touch. */
const GAP = 2;
const FLOOR = 4;
const STUB = 30;

/**
 * A small bar proof for a tile (components.md entry 18). It is hidden from assistive tech, because
 * the tile's text carries the value. The last bar is drawn in the text colour. Sizes are SVG
 * attributes, not styles, so a strict style-src still allows them.
 */
export function Spark({ values, className }: SparkProps) {
  const top = Math.max(1, ...values.filter((value): value is number => value !== null));
  const dense = values.length > DENSE_ABOVE;
  const count = Math.max(1, values.length);
  const gap = dense ? 0 : GAP;
  const barWidth = (WIDTH - gap * (count - 1)) / count;
  return (
    <svg
      className={cx("spark", dense && "spark-dense", className)}
      viewBox={`0 0 ${String(WIDTH)} 100`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      {values.map((value, index) => {
        const height = value === null ? STUB : Math.max(FLOOR, (value / top) * 100);
        return (
          <rect
            key={index}
            className={cx(
              value === null ? "spark-stub" : "spark-bar",
              index === values.length - 1 && value !== null && "spark-last",
            )}
            x={index * (barWidth + gap)}
            y={100 - height}
            width={barWidth}
            height={height}
          />
        );
      })}
    </svg>
  );
}
