import { useEffect, useRef, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../cx";
import "./ReplayLine.css";

export const states = [
  "default",
  "hover",
  "focus",
  "dragging",
  "at-start",
  "at-end",
  "long",
] as const;

/** How long after the last change the settle callback fires (the screen-reader summary line). */
export const SETTLE_MS = 500;

export interface ReplayLineProps {
  /** The accessible name, such as "Replay time". */
  label: string;
  /** Minutes from the axis start to the axis end. The range runs from 0. */
  max: number;
  /** Minutes from the axis start. */
  value: number;
  /** The time as words, such as "6:25 PM". It is the slider's `aria-valuetext`. */
  valueText: string;
  /** Minutes a Page Up or Page Down moves. 5, or `bucket_seconds / 60` when that is above 5. */
  pageStep: number;
  /** Fires on every step: a key, a drag move or a click on the rail. */
  onChange: (value: number) => void;
  /** Fires `SETTLE_MS` after the last change. */
  onSettle?: (value: number) => void;
  /** The left cell, such as "Showing 6:25 PM". */
  showing?: ReactNode;
  /** A small line under `showing`, for the bucket precision. */
  precision?: string;
  /** The key hint at the right. Hidden at phone width. */
  hint?: string;
  /** Extra classes. The component sheet uses is-hover, is-focus and is-drag. */
  className?: string;
}

const clamp = (n: number, low: number, high: number): number => Math.min(high, Math.max(low, n));

/**
 * The line that scrubs a session minute by minute in Review (components.md entry 23). The control
 * is a native range input with step 1, drawn by CSS over a transparent input that reaches 12 px
 * past the track on both sides, so the handle's centre meets 0 and 100 percent of the lanes.
 *
 * Arrow keys, Home and End are the browser's own. Page Up and Page Down are set here, because the
 * native step is a tenth of the range. The handler calls preventDefault, and the sheet's key check
 * proves in Chromium that this stops the native step.
 *
 * The visible handle carries the focus ring (`:has(input:focus-visible)`). The input keeps a
 * transparent outline of its own, which forced colours turn into a visible one.
 */
export function ReplayLine({
  label,
  max,
  value,
  valueText,
  pageStep,
  onChange,
  onSettle,
  showing,
  precision,
  hint,
  className,
}: ReplayLineProps) {
  const timer = useRef<number | undefined>(undefined);
  const settle = useRef(onSettle);
  useEffect(() => {
    settle.current = onSettle;
  });
  useEffect(
    () => () => {
      window.clearTimeout(timer.current);
    },
    [],
  );

  const change = (next: number) => {
    onChange(next);
    if (settle.current === undefined) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      settle.current?.(next);
    }, SETTLE_MS);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "PageUp" && event.key !== "PageDown") return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    const now = Number(event.currentTarget.value);
    const step = event.key === "PageUp" ? pageStep : -pageStep;
    const next = clamp(now + step, 0, max);
    if (next === now) return;
    // The page's value comes back a render later. Until it does, the next key repeat must start
    // from here, as a native arrow key does, or a fast repeat loses steps.
    event.currentTarget.value = String(next);
    change(next);
  };

  const frac = max > 0 ? clamp(value / max, 0, 1) : 0;
  return (
    <div
      className={cx("replay", className)}
      style={{ "--replay-x": `${String(frac * 100)}%` } as CSSProperties}
    >
      <div className="replay-info">
        {showing !== undefined && <span className="replay-showing">{showing}</span>}
        {precision !== undefined && <span className="replay-precision">{precision}</span>}
      </div>
      <div className="replay-track">
        <span className="replay-rail" aria-hidden="true">
          <i className="replay-fill" />
        </span>
        <i className="replay-cut" aria-hidden="true" />
        <i className="replay-handle" aria-hidden="true" />
        <input
          className="replay-input"
          type="range"
          min={0}
          max={max}
          step={1}
          value={value}
          aria-label={label}
          aria-valuetext={valueText}
          onChange={(event) => {
            change(Number(event.currentTarget.value));
          }}
          onKeyDown={onKeyDown}
        />
      </div>
      {hint !== undefined && <div className="replay-hint">{hint}</div>}
    </div>
  );
}
