import { Link } from "react-aria-components";
import { cx } from "../cx";
import { SkeletonBones } from "../SkeletonBones/SkeletonBones";
import "./Tile.css";

export const states = ["default", "proof", "unpriced", "loading", "link"] as const;

export interface TileProps {
  label: string;
  /** A short qualifier after the label, such as "API-rate estimate". */
  qualifier?: string;
  /** The headline number, already formatted. */
  value: React.ReactNode;
  /** The comparison line under the value. Replaced by the loading line while loading. */
  delta: React.ReactNode;
  /** A second line under the delta, such as "12 requests have no price". */
  note?: string;
  /** A Spark, Ring or RunDots. Hidden from assistive tech, so the text must carry the value. */
  proof?: React.ReactNode;
  /** Set while the numbers load. `label` is the one line a screen reader hears. */
  loading?: { label: string };
  /** Makes the whole tile a link to a page. Tiles only open a page, never act. */
  href?: string;
  className?: string;
}

/**
 * One headline number with its comparison and a small proof graphic (components.md entry 18). The
 * proof hides at 720 px and below. A tile that opens a page is a link.
 */
export function Tile({
  label,
  qualifier,
  value,
  delta,
  note,
  proof,
  loading,
  href,
  className,
}: TileProps) {
  const body = (
    <>
      <span className="tile-label">
        {label}
        {qualifier !== undefined && <span className="tile-qualifier">{qualifier}</span>}
      </span>
      {loading !== undefined ? (
        <SkeletonBones
          className="tile-bones"
          label={loading.label}
          bones={[{ width: "s", height: "value" }, { width: "m" }]}
        />
      ) : (
        <>
          <span className="tile-value num">{value}</span>
          <span className="tile-delta">
            {delta}
            {note !== undefined && <span className="tile-note">{note}</span>}
          </span>
          {proof !== undefined && <span className="tile-proof">{proof}</span>}
        </>
      )}
    </>
  );
  const classes = cx("tile", href !== undefined && "tile-link", className);
  if (href !== undefined) {
    return (
      <Link className={classes} href={href}>
        {body}
      </Link>
    );
  }
  return <div className={classes}>{body}</div>;
}
