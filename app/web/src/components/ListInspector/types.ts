import type { SettingStatus } from "../StatusChip/StatusChip";

/** A status the page has already worded, such as "Overridden". The chip shows the glyph and the word. */
export interface StatusWord {
  status: SettingStatus;
  label: string;
}

/** A value that can hold a secret. `masked` adds the small masked mark and its word. */
export interface ValueText {
  text: string;
  masked?: boolean;
}

/** One item in the list well. `id` is stable, so a refetch never reorders or remounts rows. */
export interface InspectorItem {
  id: string;
  name: string;
  /** One URL per item, so the inspector follows the URL. */
  href: string;
  value?: ValueText;
  status?: StatusWord;
  /** The item is read-only. The page words the lock in `lockLabel`. */
  locked?: boolean;
  /** The server did not read this item, which is neither Couldn't read nor Unknown. */
  notRead?: boolean;
  /** Matches a `ListGroup.key`. */
  group?: string;
  /** The place in a load order, drawn as a numbered circle before the name. */
  order?: number;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

/** A group heading in a long list, with its count. */
export interface ListGroup {
  key: string;
  label: string;
  count: string;
  /** Draws the group's rows with no heading. The label still names the group for the page. */
  bare?: boolean;
  /** Rows of the group the page left out, with the button that shows them. */
  more?: { label: string; onPress: () => void };
}

/** One row of the where-set well. The page passes rows in the order the top one wins. */
export interface ScopeRow {
  id: string;
  scope: { name: string; meaning: string };
  /** The setting's key at that scope, shown in code, such as `effortLevel`. */
  key?: string;
  value?: ValueText;
  status?: StatusWord;
  /** File and line, shown in code, such as `settings.local.json:3`. */
  location?: string;
  /** Words for a scope with nothing to show, such as "Not visible here". */
  note?: string;
}
