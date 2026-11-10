import { useId } from "react";
import { Switch as RacSwitch } from "react-aria-components";
import { cx } from "../cx";
import "./Switch.css";

export const states = ["off", "on", "hover", "focus", "disabled-off", "disabled-on"] as const;

export interface SwitchProps {
  /** The visible label. The whole label is the target. */
  children: React.ReactNode;
  /** Controlled, so the page can keep the state in the URL. */
  selected: boolean;
  onChange: (selected: boolean) => void;
  /** Disabled shows a dashed track, and `disabledReason` says why in visible text. */
  disabled?: boolean;
  disabledReason?: string;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

/**
 * Turns a view option on or off with an immediate effect and no Save (components.md entry 16). A
 * 40 by 24 track with a thumb, then the label. The state shows in the thumb's place as well as in
 * the track colour, and the hover halo is a shadow, so nothing moves. React Aria's Switch drops a
 * visually hidden checkbox inside the label, so Space toggles it and the label is the target.
 */
export function Switch({
  children,
  selected,
  onChange,
  disabled = false,
  disabledReason,
  className,
}: SwitchProps) {
  const reasonId = useId();
  const why = disabled && disabledReason !== undefined;
  return (
    <span className="switch-group">
      <RacSwitch
        className={cx("switch", className)}
        isSelected={selected}
        onChange={onChange}
        isDisabled={disabled}
        {...(why ? { "aria-describedby": reasonId } : {})}
      >
        <span className="switch-track" data-focus-box="" aria-hidden="true">
          <span className="switch-thumb" />
        </span>
        <span className="switch-label">{children}</span>
      </RacSwitch>
      {why && (
        <span id={reasonId} className="switch-reason">
          {disabledReason}
        </span>
      )}
    </span>
  );
}
