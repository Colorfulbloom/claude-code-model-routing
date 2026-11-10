import { useRef } from "react";
import { cx } from "../cx";
import { Inspector, type InspectorProps } from "./Inspector";
import { ItemList, type ItemListProps } from "./ItemList";
import "./ListInspector.css";

export type { InspectorItem, ListGroup, ScopeRow, StatusWord, ValueText } from "./types";
export { Inspector, type InspectorProps } from "./Inspector";
export { ItemList, type ItemListProps } from "./ItemList";

export const states = [
  "list",
  "hover",
  "focus",
  "selected",
  "selected-focus",
  "read-only",
  "not-read",
  "unknown",
  "couldnt-read",
  "masked",
  "empty",
  "grouped",
  "long-values",
  "phone-list",
  "phone-inspector",
] as const;

export interface ListInspectorProps {
  list: Omit<ItemListProps, "onOpen">;
  /** Null while nothing is picked, or when the picked item is gone. */
  inspector: Omit<InspectorProps, "headingRef" | "back" | "focusOnMount"> | null;
  /**
   * `split` shows both cards side by side (one column at 720 px and below). On a phone the page
   * picks `list`, where the list is the page, or `inspector`, where the inspector is its own page
   * with a back link to the list.
   */
  mode?: "split" | "list" | "inspector";
  /** The back link of the phone inspector page. */
  back?: { label: string; href: string };
  /** Called when a person picks an item, before focus moves to the inspector heading. */
  onOpen?: (id: string) => void;
  className?: string;
}

/**
 * Level 3 of the setup (components.md entry 26): the item list on the left and the inspector on
 * the right, 340 px and fluid (280 px below 1100 px). The list is a `nav` of links, one URL per
 * item, so the inspector follows the URL. Opening an item moves focus to the inspector's h2.
 * The phone inspector page focuses its h2 on mount instead, because the list is gone by then.
 */
export function ListInspector({
  list,
  inspector,
  mode = "split",
  back,
  onOpen,
  className,
}: ListInspectorProps) {
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const handleOpen = (id: string) => {
    onOpen?.(id);
    queueMicrotask(() => {
      headingRef.current?.focus();
    });
  };
  return (
    <div
      className={cx("list-inspector", mode !== "split" && "list-inspector-single", className)}
      data-mode={mode}
    >
      {mode !== "inspector" && <ItemList {...list} onOpen={handleOpen} />}
      {mode !== "list" && inspector !== null && (
        <Inspector
          {...inspector}
          headingRef={headingRef}
          {...(mode === "inspector" ? { focusOnMount: true } : {})}
          {...(mode === "inspector" && back !== undefined ? { back } : {})}
        />
      )}
    </div>
  );
}
