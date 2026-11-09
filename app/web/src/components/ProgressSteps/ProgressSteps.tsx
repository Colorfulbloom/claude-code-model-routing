import { Label, ProgressBar } from "react-aria-components";
import { cx } from "../cx";
import { RunStateGlyph, type RunState } from "../RunStateGlyph/RunStateGlyph";
import "../Well/Well.css";
import "./ProgressSteps.css";

export const states = ["done", "in-progress", "next", "failed"] as const;

export type StepState = "done" | "current" | "next" | "failed";

export interface ProgressStep {
  id: string;
  name: string;
  state: StepState;
  /** The word for the state, such as "Done", "In progress", "Next" or "Failed". */
  stateWord: string;
  /** Only for the current step. `percent` is 0 to 100, `text` is the size line, such as "41 of 82 MB". */
  progress?: {
    percent: number;
    text: string;
    /** The text is a polite status of its own, such as a retry line. */ live?: boolean;
  };
  /** A muted line under the step name with no bar, such as "640 of 1,240 files" on a failed step. */
  note?: string;
}

export interface ProgressStepsProps {
  /** Accessible name of the list. */
  label: string;
  steps: ProgressStep[];
  className?: string;
}

const glyphs: Record<StepState, RunState> = {
  done: "done",
  current: "working",
  next: "idle",
  failed: "failed",
};

/** A known sequence of setup steps (components.md entry 34). The current step is announced politely. */
export function ProgressSteps({ label, steps, className }: ProgressStepsProps) {
  const current = steps.find((step) => step.state === "current");
  return (
    <>
      <ol className={cx("progress-steps", "well", className)} aria-label={label}>
        {steps.map((step) => (
          <li
            key={step.id}
            className="progress-step"
            aria-current={step.state === "current" ? "step" : undefined}
          >
            <RunStateGlyph state={glyphs[step.state]}>{step.stateWord}</RunStateGlyph>
            <span className="progress-step-name">{step.name}</span>
            {step.note !== undefined && (
              <small className="progress-step-value progress-step-note muted num">
                {step.note}
              </small>
            )}
            {step.progress !== undefined && (
              <ProgressBar
                className="progress-step-bar"
                value={step.progress.percent}
                valueLabel={step.progress.text}
              >
                {({ percentage }) => (
                  <>
                    <Label className="sr-only">{step.name}</Label>
                    {/* Width is an SVG attribute, not a style, so a strict style-src still allows it. */}
                    <svg className="progress-step-track" aria-hidden="true" height="8">
                      <rect className="progress-step-rail" width="100%" height="8" rx="4" />
                      <rect
                        className="progress-step-fill"
                        width={`${percentage}%`}
                        height="8"
                        rx="4"
                      />
                    </svg>
                    <span
                      className="progress-step-value muted num"
                      role={step.progress?.live === true ? "status" : undefined}
                    >
                      {step.progress?.text}
                    </span>
                  </>
                )}
              </ProgressBar>
            )}
          </li>
        ))}
      </ol>
      <p className="sr-only" role="status">
        {current !== undefined ? `${current.stateWord}: ${current.name}` : ""}
      </p>
    </>
  );
}
