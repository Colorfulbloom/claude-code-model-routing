import { Button } from "../Button/Button";
import { cx } from "../cx";
import { HelpButton } from "../HelpButton/HelpButton";
import { PageHeader } from "../PageHeader/PageHeader";
import { Select, type SelectOption } from "../Select/Select";
import "./ScopeBar.css";

export const states = [
  "range",
  "range-hover",
  "range-focus",
  "session",
  "session-hover",
  "session-focus",
  "session-no-live",
  "with-pages",
] as const;

/** The range form: a Select used as the Range Select. */
export interface ScopeBarRange {
  /** The muted label inside the Select, such as "Range". */
  label: string;
  /** The presets, passed in with their words. Review has six. */
  options: SelectOption[];
  value: string | null;
  onChange: (id: string) => void;
  /** Extra classes on the Select. The component sheet uses is-hover and is-focus. */
  className?: string;
}

/** A link in the session form. */
export interface ScopeBarLink {
  label: string;
  href: string;
  /** Extra classes. The component sheet uses is-hover and is-focus. */
  className?: string;
}

export type ScopeBarForm =
  | { form: "range"; range: ScopeBarRange }
  | {
      form: "session";
      /** The back link to Sessions. */
      back: ScopeBarLink;
      /** The Session Select, built by the caller. */
      sessionSelect: React.ReactNode;
      /** Open in Live. The caller leaves it out when the session has ended. */
      openLive?: ScopeBarLink;
    };

export type ScopeBarProps = ScopeBarForm & {
  title: string;
  /** The range dates, or "This session is still running". */
  sub?: string;
  /**
   * The phone Segmented pages. They sit under the bar. The caller passes them at 720px and below
   * only, because the sidebar carries the pages above that.
   */
  pages?: React.ReactNode;
  className?: string;
};

/**
 * Sets what a Review page shows: a range (the default is the last 30 days) or one session
 * (components.md entry 4). It is always the top of a Review page. The controls sit on the right and
 * wrap under the title at 720px and below, as the page header's controls do. Every word comes in
 * through props.
 */
export function ScopeBar(props: ScopeBarProps) {
  const { title, sub, pages, className } = props;
  const controls =
    props.form === "range" ? (
      <>
        <Select
          label={props.range.label}
          items={props.range.options}
          value={props.range.value}
          onChange={props.range.onChange}
          heading={props.range.label}
          rangePopover
          className={cx("scope-bar-range", props.range.className)}
        />
        <HelpButton help="shell.range" />
      </>
    ) : (
      <>
        <Button
          variant="quiet"
          href={props.back.href}
          {...(props.back.className !== undefined ? { className: props.back.className } : {})}
        >
          {props.back.label}
        </Button>
        {props.sessionSelect}
        {props.openLive !== undefined && (
          <Button
            href={props.openLive.href}
            {...(props.openLive.className !== undefined
              ? { className: props.openLive.className }
              : {})}
          >
            {props.openLive.label}
          </Button>
        )}
      </>
    );
  return (
    <div className={cx("scope-bar", className)} data-form={props.form}>
      <PageHeader title={title} {...(sub !== undefined ? { sub } : {})} controls={controls} />
      {pages !== undefined && <div className="scope-bar-pages">{pages}</div>}
    </div>
  );
}
