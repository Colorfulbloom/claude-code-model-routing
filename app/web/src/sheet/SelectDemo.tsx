import { useState } from "react";
import { Select, SelectList, type SelectOption } from "@/components/Select/Select";
import { W } from "./words";

export interface SelectDemoProps {
  label: string;
  items: SelectOption[];
  initial: string;
  state?: "default" | "hover" | "focus" | "open" | "disabled";
}

/**
 * A Select with its own state, for the sheet. The open state renders the listbox in place, because a
 * real popover would cover the rest of the sheet.
 */
export function SelectDemo({ label, items, initial, state = "default" }: SelectDemoProps) {
  const [value, setValue] = useState<string | null>(initial);
  if (state === "open") {
    return (
      <div className="sheet-open-select">
        <Select
          label={label}
          items={items}
          value={value}
          onChange={setValue}
          className="is-hover"
        />
        <SelectList
          items={items}
          className="select-list-static"
          aria-label={label}
          selectedKeys={value === null ? [] : [value]}
        />
      </div>
    );
  }
  const forced = state === "hover" ? "is-hover" : state === "focus" ? "is-focus" : undefined;
  return (
    <Select
      label={label}
      items={items}
      value={value}
      onChange={setValue}
      isDisabled={state === "disabled"}
      {...(state === "disabled" ? { disabledReason: W.rk_note } : {})}
      {...(forced !== undefined ? { className: forced } : {})}
    />
  );
}
