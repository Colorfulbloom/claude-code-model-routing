/*
 * Whole-row targets for the plain review tables. A row's name is one real link and the one Tab
 * stop. A click on any other part of the row forwards to that link, so the row does what the name
 * does. The forward is a click event on the link itself, so a Cmd or Ctrl click opens a new tab and a
 * middle click opens one too, exactly as on the name. A click is left alone when it lands on another
 * control, when the pointer dragged, or when text is selected in the row, so selecting text never
 * navigates. The row gets no role and no tabindex.
 */
import { useRef } from "react";

/** Anything in a row that handles its own click. The row never forwards a click that starts here. */
const OWN_CLICK = "a, button, input, select, textarea, summary, label, [role='button'], [tabindex]";

/** How far a pointer may move between press and release and still count as a click, in pixels. */
const DRAG_PX = 4;

/** The props that make a table row open its link. Spread them on the `tr`. */
export interface RowLinkProps {
  "data-row-link": "";
  onPointerDown: (event: React.PointerEvent<HTMLTableRowElement>) => void;
  onClick: (event: React.MouseEvent<HTMLTableRowElement>) => void;
  onAuxClick: (event: React.MouseEvent<HTMLTableRowElement>) => void;
}

function selectionInside(row: HTMLElement): boolean {
  const selection = window.getSelection();
  if (selection === null || selection.isCollapsed || selection.toString() === "") return false;
  return (
    (selection.anchorNode !== null && row.contains(selection.anchorNode)) ||
    (selection.focusNode !== null && row.contains(selection.focusNode))
  );
}

export function useRowLink(): RowLinkProps {
  const down = useRef<{ x: number; y: number } | null>(null);

  const forward = (
    event: React.MouseEvent<HTMLTableRowElement>,
    init: { ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; altKey: boolean },
  ) => {
    const row = event.currentTarget;
    const target = event.target;
    if (!(target instanceof Element) || event.defaultPrevented) return;
    const own = target.closest(OWN_CLICK);
    if (own !== null && row.contains(own)) return;
    const start = down.current;
    down.current = null;
    if (start !== null && Math.hypot(event.clientX - start.x, event.clientY - start.y) > DRAG_PX) {
      return;
    }
    if (selectionInside(row)) return;
    const link = row.querySelector<HTMLAnchorElement>("a[href]");
    if (link === null) return;
    link.dispatchEvent(
      new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: window,
        button: 0,
        ...init,
      }),
    );
  };

  return {
    "data-row-link": "",
    onPointerDown: (event) => {
      down.current = { x: event.clientX, y: event.clientY };
    },
    onClick: (event) => {
      forward(event, {
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
        shiftKey: event.shiftKey,
        altKey: event.altKey,
      });
    },
    onAuxClick: (event) => {
      if (event.button !== 1) return;
      // A middle click opens a background tab, the same as a Cmd or Ctrl click on the link.
      forward(event, { ctrlKey: true, metaKey: true, shiftKey: false, altKey: false });
    },
  };
}
