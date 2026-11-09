import { cx } from "../cx";
import "./ModelSwatch.css";

export const states = ["opus", "sonnet", "haiku", "fable"] as const;

export type Model = (typeof states)[number];

export interface ModelSwatchProps {
  model: Model;
  className?: string;
}

/**
 * Marks a model wherever its colour is used (components.md entry 36). Opus is a square, Sonnet a
 * circle, Haiku a diamond and Fable a triangle (owner decision D9). It always sits beside the
 * model name, so it is hidden from assistive tech.
 */
export function ModelSwatch({ model, className }: ModelSwatchProps) {
  return (
    <span className={cx("model-swatch", `model-swatch-${model}`, className)} aria-hidden="true" />
  );
}
