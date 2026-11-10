import { useId } from "react";
import {
  Button as AriaButton,
  Collection,
  Header,
  Label,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  Popover,
  Select as AriaSelect,
  SelectValue,
  Text,
} from "react-aria-components";
import { cx } from "../cx";
import "./Select.css";

export const states = ["default", "hover", "focus", "open", "disabled"] as const;

export interface SelectOption {
  id: string;
  /** The name. It is also the text the closed button shows. */
  label: string;
  /** A second block in muted text. It stays out of the closed button. */
  description?: React.ReactNode;
  /** A group heading. Items with the same heading sit together, in the order the groups first appear. */
  group?: string;
}

export interface SelectProps {
  /** Muted label shown inside the button, and the accessible name. */
  label: string;
  items: SelectOption[];
  value: string | null;
  onChange: (id: string) => void;
  placeholder?: string;
  isDisabled?: boolean;
  /** Visible reason, tied to the control with aria-describedby. Use with isDisabled. */
  disabledReason?: string;
  /** A small heading above the list inside the popover, such as "Projects". */
  heading?: string;
  /** Shown in place of the list when there are no items. */
  emptyState?: React.ReactNode;
  /** Fills its container with the label above the value, and opens a 360px popover under the left edge. */
  stacked?: boolean;
  /**
   * Opens a fixed-width popover (340px) under the trigger's right edge, as the Review Range Select
   * does on a wide screen. At 720px and below the tray is unchanged.
   */
  rangePopover?: boolean;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

function OptionItem({ item }: { item: SelectOption }) {
  return (
    <ListBoxItem id={item.id} textValue={item.label} className="select-option">
      <Text slot="label" className="select-option-label">
        {item.label}
      </Text>
      {item.description !== undefined && (
        <Text slot="description" className="select-option-description" elementType="div">
          {item.description}
        </Text>
      )}
    </ListBoxItem>
  );
}

/** Items grouped by heading, in the order the headings first appear. */
function groupItems(items: SelectOption[]): { heading: string; items: SelectOption[] }[] {
  const groups: { heading: string; items: SelectOption[] }[] = [];
  for (const item of items) {
    const heading = item.group ?? "";
    const found = groups.find((group) => group.heading === heading);
    if (found === undefined) groups.push({ heading, items: [item] });
    else found.items.push(item);
  }
  return groups;
}

/** The options of a Select. It also renders on its own, which the component sheet and the tray use. */
export function SelectList({
  items,
  className,
  emptyState,
  onChange,
  ...rest
}: {
  items: SelectOption[];
  className?: string;
  "aria-label"?: string;
  selectedKeys?: string[];
  /** Standalone lists only. Inside a Select the Select owns the selection. */
  onChange?: (id: string) => void;
  autoFocus?: boolean;
  emptyState?: React.ReactNode;
}) {
  const grouped = items.some((item) => item.group !== undefined);
  const shared = {
    className: cx("select-list", className),
    ...(onChange !== undefined
      ? {
          selectionMode: "single" as const,
          disallowEmptySelection: true,
          onSelectionChange: (keys: "all" | Set<React.Key>) => {
            const [first] = keys === "all" ? [] : [...keys];
            if (first !== undefined) onChange(String(first));
          },
        }
      : {}),
    ...(emptyState !== undefined ? { renderEmptyState: () => emptyState } : {}),
    ...rest,
  };
  if (grouped) {
    return (
      <ListBox {...shared}>
        {groupItems(items).map((group) => (
          <ListBoxSection key={group.heading} className="select-section">
            <Header className="select-group-heading">{group.heading}</Header>
            <Collection items={group.items}>{(item) => <OptionItem item={item} />}</Collection>
          </ListBoxSection>
        ))}
      </ListBox>
    );
  }
  return (
    <ListBox items={items} {...shared}>
      {(item) => <OptionItem item={item} />}
    </ListBox>
  );
}

/**
 * Picks one value from a list (components.md entry 14). At 720px and below the popover renders
 * as a bottom tray that covers the tab bar, through a media query in Select.css.
 *
 * Disabled renders a plain button with aria-disabled, not React Aria's native disabled one, so the
 * control stays focusable and its reason is read through aria-describedby (shared rule, Disabled).
 */
export function Select({
  label,
  items,
  value,
  onChange,
  placeholder,
  isDisabled = false,
  disabledReason,
  heading,
  emptyState,
  stacked = false,
  rangePopover = false,
  className,
}: SelectProps) {
  const reasonId = useId();
  const headingId = useId();
  const labelId = useId();
  const valueId = useId();
  if (isDisabled) {
    const shown = items.find((item) => item.id === value)?.label ?? placeholder ?? "";
    return (
      <div className={cx("select", stacked && "select-stacked", className)}>
        <button
          type="button"
          className="select-btn"
          aria-disabled="true"
          aria-describedby={disabledReason !== undefined ? reasonId : undefined}
        >
          <span className="select-label">{label}</span>
          <span className="select-value">{shown}</span>
          <span className="select-chevron" aria-hidden="true" />
        </button>
        {disabledReason !== undefined && (
          <span id={reasonId} className="select-reason">
            {disabledReason}
          </span>
        )}
      </div>
    );
  }
  return (
    <AriaSelect
      className={cx("select", stacked && "select-stacked", className)}
      selectedKey={value}
      allowsEmptyCollection
      onSelectionChange={(key) => {
        if (key !== null) onChange(String(key));
      }}
      {...(placeholder !== undefined ? { placeholder } : {})}
    >
      {/* The name reads label first, then value: "Project, Pick a project". */}
      <AriaButton className="select-btn" aria-labelledby={`${labelId} ${valueId}`}>
        <Label className="select-label" id={labelId}>
          {label}
        </Label>
        <SelectValue className="select-value" id={valueId}>
          {({ selectedText, defaultChildren, isPlaceholder }) =>
            isPlaceholder ? defaultChildren : selectedText
          }
        </SelectValue>
        <span className="select-chevron" aria-hidden="true" />
      </AriaButton>
      <Popover
        className={cx(
          "select-popover",
          stacked && "select-popover-wide",
          rangePopover && "select-popover-range",
        )}
        {...(stacked ? { placement: "bottom start" as const, offset: 4 } : {})}
        {...(rangePopover ? { placement: "bottom end" as const, offset: 4 } : {})}
      >
        {heading !== undefined && (
          <p className="select-heading" id={headingId}>
            {heading}
          </p>
        )}
        <SelectList items={items} {...(emptyState !== undefined ? { emptyState } : {})} />
      </Popover>
    </AriaSelect>
  );
}
