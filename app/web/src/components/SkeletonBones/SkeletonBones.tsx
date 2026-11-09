import { cx } from "../cx";
import "./SkeletonBones.css";

export const states = ["text", "value", "rows"] as const;

export interface Bone {
  /** Width preset. Widths are classes, not inline styles, so a strict style-src still allows them. */
  width: "xs" | "s" | "m" | "l" | "full";
  height?: "text" | "value";
}

export interface SkeletonBonesProps {
  /** The one line a screen reader hears while the region loads. */
  label: string;
  bones: Bone[];
  className?: string;
}

/**
 * Loading placeholders at the height of the loaded content (components.md entry 37). The bones are
 * hidden from assistive tech, the region is aria-busy, and the label is the only spoken line.
 */
export function SkeletonBones({ label, bones, className }: SkeletonBonesProps) {
  return (
    <div className={cx("skeleton", className)} aria-busy="true">
      <p className="sr-only">{label}</p>
      {bones.map((bone, index) => (
        <i
          key={index}
          className={cx("bone", `bone-${bone.width}`, bone.height === "value" && "bone-value")}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
