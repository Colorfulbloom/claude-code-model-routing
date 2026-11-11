import { Fragment } from "react";
import { splitPath } from "@/lib/edit-words";
import { cx } from "../cx";
import "./Diff.css";

export interface PathTextProps {
  /** A display path, such as ~/work/tidewater-reporting/.claude/settings.local.json. */
  path: string;
  className?: string;
}

/**
 * A file path in the mono face with its folder muted and its file name in bold. A break point
 * follows each slash, so a long path wraps at a folder and never scrolls sideways. The text is the
 * whole path, so a screen reader reads it as one.
 */
export function PathText({ path, className }: PathTextProps) {
  const { dir, name } = splitPath(path);
  const parts = dir.split("/").slice(0, -1);
  return (
    <span className={cx("path-text", className)}>
      <span className="path-text-dir">
        {parts.map((part, i) => (
          <Fragment key={`${String(i)}-${part}`}>
            {part}/<wbr />
          </Fragment>
        ))}
      </span>
      <b className="path-text-name">{name}</b>
    </span>
  );
}
