import { Link } from "react-aria-components";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import type { HelpId } from "@/strings/help";
import { cx } from "../cx";
import { SkeletonBones } from "../SkeletonBones/SkeletonBones";
import "./Tile.css";

export const states = [
  "default",
  "proof",
  "unpriced",
  "loading",
  "link",
  "help",
  "link-help",
] as const;

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
  /** A "?" at the end of the label row that opens this help entry. `values` are the numbers on the tile. */
  help?: { id: HelpId; values?: Readonly<Record<string, string>> };
  className?: string;
}

/**
 * One headline number with its comparison and a small proof graphic (components.md entry 18). The
 * proof hides at 720 px and below. A tile that opens a page puts only its label in the link and
 * stretches the link over the whole tile, so the link's name is the label and the numbers follow
 * as plain text. The "?" is a sibling of that link, above it, so it never sits inside a link.
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
  help,
  className,
}: TileProps) {
  const classes = cx(
    "tile",
    href !== undefined && "tile-link",
    help !== undefined && "tile-has-help",
    className,
  );
  return (
    <div className={classes}>
      <span className="tile-label">
        {href === undefined ? (
          label
        ) : (
          <Link className="tile-link-label" href={href}>
            {label}
          </Link>
        )}
        {qualifier !== undefined && <span className="tile-qualifier">{qualifier}</span>}
        {help !== undefined && (
          <HelpButton
            className="tile-help"
            help={help.id}
            {...(help.values === undefined ? {} : { values: help.values })}
          />
        )}
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
    </div>
  );
}
