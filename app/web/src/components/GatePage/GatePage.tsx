import { cx } from "../cx";
import "../Card/Card.css";
import "./GatePage.css";

export const states = [
  "default",
  "locked-no-key",
  "locked-code-used",
  "locked-code-expired",
  "locked-server-restarted",
  "first-run-failed",
] as const;

export interface GatePageProps {
  brand: string;
  /** The card body. It brings its own h1. */
  children: React.ReactNode;
  /** A polite notice above the card, such as the new-tab line. */
  notice?: React.ReactNode;
  /** The route harness reads the card's h1 through this ref. */
  ref?: React.Ref<HTMLDivElement>;
  className?: string;
}

/** A bare page for the locked tab and first run: no shell, one centred card (components.md entry 35). */
export function GatePage({ brand, children, notice, ref, className }: GatePageProps) {
  return (
    <div className={cx("gate-page", className)} ref={ref}>
      <header className="gate-brand brand">{brand}</header>
      <main className="gate-main">
        {notice !== undefined && <div className="gate-notice">{notice}</div>}
        <div className="card gate-card">{children}</div>
      </main>
    </div>
  );
}
