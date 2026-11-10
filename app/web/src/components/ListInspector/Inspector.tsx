import { useEffect, useId, useRef } from "react";
import { Link } from "react-aria-components";
import { CommandRow } from "../CommandRow/CommandRow";
import { CopyPath } from "../CopyPath/CopyPath";
import { cx } from "../cx";
import { RaisedFinding } from "../RaisedFinding/RaisedFinding";
import { ScopeLabel } from "../ScopeLabel/ScopeLabel";
import { StatusChip } from "../StatusChip/StatusChip";
import { Well } from "../Well/Well";
import type { ScopeRow, StatusWord } from "./types";
import { ValueText } from "./ValueText";
import "../Card/Card.css";
import "./ListInspector.css";

export interface InspectorReadOnly {
  /** The word on the lock mark, such as "Read only". */
  lockLabel: string;
  /** The owner's reason, such as "Your organization manages this file, so the dashboard can't change it." */
  reason: string;
  /** The command that changes it from a terminal, when the dashboard can't write it. */
  command?: { command: string; copyLabel: string; copiedLabel: string };
  /** The file's full path, for Copy path. */
  path?: { value: string; label: string; copiedLabel: string; ariaLabel?: string };
}

export interface InspectorNotRead {
  /** The Unknown pill the sentence starts with, because Bar Tab can't tell what the item adds. */
  status: StatusWord;
  /** Why, such as "This file sits outside the folders Bar Tab reads for this project." */
  body: string;
}

export interface InspectorProps {
  /** The h2 text, the name of the item. It also names the region. */
  title: string;
  status?: StatusWord;
  /** Gets focus when a person opens an item with Enter. The heading takes `tabIndex={-1}`. */
  headingRef?: React.RefObject<HTMLHeadingElement | null>;
  /** Moves focus to the heading once, on mount. The phone inspector page uses it. */
  focusOnMount?: boolean;
  /** Phone page only. A link back to the list. */
  back?: { label: string; href: string };
  /** The "Runs at" line. */
  runs?: React.ReactNode;
  /** The "Set to X in file, line N" line. */
  setTo?: React.ReactNode;
  readOnly?: InspectorReadOnly;
  /** An item the server did not read. Its box sits under the headline, with the Unknown pill. */
  notRead?: InspectorNotRead;
  /** A callout under the headline for an item that doesn't run as set, such as an agent's check. */
  check?: React.ReactNode;
  /** The facts that differ by kind, such as an agent's fields. They sit above the where-set well. */
  details?: React.ReactNode;
  /** Words for the where-set well. The rows come in the order the top one wins. */
  where?: { title: string; rows: ScopeRow[]; maskedLabel: string };
  /** The Why block, raised, with an optional confidence line. */
  why?: { title: string; body: React.ReactNode; confidence?: string };
  usage?: React.ReactNode;
  /** A finding the page raises about the item, such as Couldn't read, above the facts. */
  finding?: React.ReactNode;
  /** Buttons at the foot, such as Edit and Copy path. */
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

function LockIcon() {
  return (
    <svg
      className="inspector-lock"
      viewBox="0 0 12 14"
      width="11"
      height="13"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor" />
      <path
        d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

/**
 * The inspector card of the list and inspector (components.md entry 26): a labelled region with an
 * h2 and the status, then slots for the runs-at line, the set-to line, the where-set well, Why, usage
 * and actions. A read-only item shows the lock mark, the owner's reason, an optional command row
 * and Copy path. The page fills the slots, and every word comes in through props.
 */
export function Inspector({
  title,
  status,
  headingRef,
  focusOnMount = false,
  back,
  runs,
  setTo,
  readOnly,
  notRead,
  check,
  details,
  where,
  why,
  usage,
  finding,
  actions,
  children,
  className,
}: InspectorProps) {
  const headingId = useId();
  const ownRef = useRef<HTMLHeadingElement | null>(null);
  const ref = headingRef ?? ownRef;

  useEffect(() => {
    if (focusOnMount) ref.current?.focus();
  }, [focusOnMount, ref]);

  return (
    <section className={cx("card", "inspector", className)} aria-labelledby={headingId}>
      {back !== undefined && (
        <Link className="inspector-back" href={back.href}>
          <span aria-hidden="true">←</span> {back.label}
        </Link>
      )}
      <header className="inspector-head">
        <h2 className="inspector-title" id={headingId} ref={ref} tabIndex={-1}>
          {title}
        </h2>
        {status !== undefined && <StatusChip status={status.status}>{status.label}</StatusChip>}
      </header>
      <div className="inspector-body">
        {finding}
        {runs !== undefined && <p className="inspector-runs">{runs}</p>}
        {setTo !== undefined && <p className="inspector-set">{setTo}</p>}
        {notRead !== undefined && (
          <RaisedFinding className="inspector-not-read">
            <p className="inspector-not-read-line">
              <StatusChip status={notRead.status.status}>{notRead.status.label}</StatusChip>
              {notRead.body}
            </p>
          </RaisedFinding>
        )}
        {check}
        {readOnly !== undefined && (
          <RaisedFinding className="inspector-readonly">
            <p className="inspector-readonly-reason">
              <LockIcon />
              <span className="sr-only">{readOnly.lockLabel}. </span>
              {readOnly.reason}
            </p>
            {readOnly.command !== undefined && (
              <CommandRow
                command={readOnly.command.command}
                copyLabel={readOnly.command.copyLabel}
                copiedLabel={readOnly.command.copiedLabel}
              />
            )}
            {readOnly.path !== undefined && (
              <CopyPath
                value={readOnly.path.value}
                label={readOnly.path.label}
                copiedLabel={readOnly.path.copiedLabel}
                {...(readOnly.path.ariaLabel !== undefined
                  ? { ariaLabel: readOnly.path.ariaLabel }
                  : {})}
              />
            )}
          </RaisedFinding>
        )}
        {details}
        {where !== undefined && (
          <div className="inspector-where">
            <h3 className="inspector-h3">{where.title}</h3>
            <Well variant="list">
              <ul className="where-list">
                {where.rows.map((row) => (
                  <li key={row.id} className="where-row">
                    <ScopeLabel name={row.scope.name} meaning={row.scope.meaning} />
                    {row.key !== undefined && <code className="where-key">{row.key}</code>}
                    {row.value !== undefined && (
                      <b className="where-value">
                        <ValueText value={row.value} maskedLabel={where.maskedLabel} />
                      </b>
                    )}
                    {row.note !== undefined && <span className="where-note muted">{row.note}</span>}
                    {row.status !== undefined && (
                      <StatusChip status={row.status.status}>{row.status.label}</StatusChip>
                    )}
                    {row.location !== undefined && (
                      <code className="where-location muted">{row.location}</code>
                    )}
                  </li>
                ))}
              </ul>
            </Well>
          </div>
        )}
        {why !== undefined && (
          <RaisedFinding title={why.title} className="inspector-why">
            <p>{why.body}</p>
            {why.confidence !== undefined && (
              <p className="inspector-small muted">{why.confidence}</p>
            )}
          </RaisedFinding>
        )}
        {usage !== undefined && <p className="inspector-small muted">{usage}</p>}
        {children}
        {actions !== undefined && <div className="inspector-actions">{actions}</div>}
      </div>
    </section>
  );
}
