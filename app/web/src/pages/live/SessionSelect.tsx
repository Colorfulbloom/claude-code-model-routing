import { useRef, useState } from "react";
import {
  Button as AriaButton,
  Dialog,
  DialogTrigger,
  Heading,
  Link,
  Popover,
} from "react-aria-components";
import { cx } from "@/components/cx";
import { SelectList, type SelectOption } from "@/components/Select/Select";
import { useIsDesktop } from "@/lib/media";
import "./SessionSelect.css";

export interface SessionSelectProps {
  /** The muted word in the button, "Session". It reads first in the accessible name. */
  label: string;
  /** The value shown in the closed button, such as "feature/quarter-close, 6:10 PM". */
  valueLabel: string;
  /** The value is a prompt such as "None running", so it shows muted. */
  placeholder?: boolean;
  /** The popover's heading, "Sessions". It names the dialog. */
  heading: string;
  /** Options with a `group` heading each. */
  items: SelectOption[];
  value: string | null;
  onChange: (id: string) => void;
  /** The "See all sessions" link. It is at least 26px tall. */
  all: { label: string; href: string };
  closeLabel: string;
  className?: string;
}

/**
 * Picks a session (components.md entries 14 and 51). The popover is a dialog that holds the grouped
 * listbox and a link to every session, so it opens as a popover at 721px and up and as a bottom
 * tray at 720px and below, through Select.css. The visible words are the button's name.
 */
export function SessionSelect({
  label,
  valueLabel,
  placeholder = false,
  heading,
  items,
  value,
  onChange,
  all,
  closeLabel,
  className,
}: SessionSelectProps) {
  const [open, setOpen] = useState(false);
  const desktop = useIsDesktop();
  // The popover hangs from the header's whole control group (Select, status and Pause), so its
  // right edge lines up with Pause, as the board draws it. Without a group it hangs from the button.
  const anchor = useRef<HTMLElement | null>(null);
  return (
    <DialogTrigger isOpen={open} onOpenChange={setOpen}>
      <AriaButton
        className={cx("select-btn", "session-select-btn", className)}
        ref={(button) => {
          anchor.current = button?.closest<HTMLElement>(".live-controls") ?? button;
        }}
      >
        <span className="select-label">{label}</span>
        <span className={cx("select-value", placeholder && "session-select-placeholder")}>
          {valueLabel}
        </span>
        <span className="select-chevron" aria-hidden="true" />
      </AriaButton>
      <Popover
        className="select-popover session-select-popover"
        placement="bottom end"
        triggerRef={anchor}
        offset={desktop ? 24 : 4}
      >
        <Dialog className="session-select-dialog" aria-label={heading}>
          <div className="session-select-head">
            <Heading slot="title" className="session-select-heading">
              {heading}
            </Heading>
            <AriaButton slot="close" className="session-select-close" aria-label={closeLabel}>
              {"✕"}
            </AriaButton>
          </div>
          <SelectList
            items={items}
            aria-label={heading}
            selectedKeys={value === null ? [] : [value]}
            onChange={(id) => {
              setOpen(false);
              onChange(id);
            }}
            {...{ autoFocus: true }}
          />
          <Link className="session-select-all" href={all.href}>
            {all.label}
            <span aria-hidden="true">{" →"}</span>
          </Link>
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
