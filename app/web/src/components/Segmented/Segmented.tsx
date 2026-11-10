import { Link } from "react-aria-components";
import { cx } from "../cx";
import "./Segmented.css";

export const states = ["default", "hover", "focus", "selected", "overflow"] as const;

export interface SegmentedItem {
  id: string;
  href: string;
  label: string;
  /** The page the person is on. It gets `aria-current="page"` and the chosen look. */
  current?: boolean;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

export interface SegmentedProps {
  /** Names the nav landmark, such as "Review pages". */
  label: string;
  items: SegmentedItem[];
  className?: string;
}

/**
 * The pages variant of the segmented control (components.md entry 13): in-page navigation, such as
 * the Review views at 375. It is a `nav` of links, and the current one carries `aria-current="page"`.
 * The chosen look is the canonical one, a --select-bg fill with a 2px --accent edge and semibold
 * text, with no check because it is navigation. Segments never wrap, so a row that doesn't fit
 * scrolls sideways. The choice variant (a RadioGroup) is not built yet.
 */
export function Segmented({ label, items, className }: SegmentedProps) {
  return (
    <nav className={cx("segmented", className)} aria-label={label}>
      <ul className="segmented-track">
        {items.map((item) => (
          <li key={item.id} className="segmented-item">
            <Link
              className={cx("segmented-link", item.className)}
              href={item.href}
              {...(item.current === true ? { "aria-current": "page" as const } : {})}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
