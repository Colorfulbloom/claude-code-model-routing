import { useId } from "react";
import { Link } from "react-aria-components";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { EmptyState } from "../EmptyState/EmptyState";
import { StatusChip } from "../StatusChip/StatusChip";
import { Well } from "../Well/Well";
import type { InspectorItem, ListGroup } from "./types";
import { ValueText } from "./ValueText";
import "../Card/Card.css";
import "./ListInspector.css";

export interface ItemListEmpty {
  /** Says what would appear, such as "No hooks yet. Hooks you add show up here." */
  text: string;
  /** Left out when nothing can fill the list from here, such as a part Bar Tab can't see. */
  actionLabel?: string;
  href?: string;
  onPress?: () => void;
}

/** Jump to chips for a long list. The page shows them only for the exceptions. */
export interface ItemListJump {
  /** The word before the chips, such as "Jump to". */
  label: string;
  chips: { key: string; label: string; count: string; onPress: () => void }[];
}

export interface ItemListProps {
  /** The h2 and the name of the nav landmark, such as "Settings". */
  title: string;
  /** The item count next to the title, tabular and muted. */
  count?: string;
  items: InspectorItem[];
  /** Headings and counts for a long list, in order. Items with no group follow the last one. */
  groups?: ListGroup[];
  /** The id of the item the URL names. It gets the chosen state and `aria-current`. */
  selectedId?: string;
  /** The word on the lock mark, such as "Read only". */
  lockLabel: string;
  /** The word on the masked mark, such as "Masked". */
  maskedLabel: string;
  /** The words for an item the server did not read, such as "Not read here". */
  notReadLabel: string;
  /** Shown in place of the list when there are no items. One sentence and one action. */
  empty?: ItemListEmpty;
  /** Called when a person picks an item by pointer or by Enter. The page moves focus to the inspector heading. */
  onOpen?: (id: string) => void;
  /** A finding the page raises over the list, such as Couldn't read, above the rows. */
  pre?: React.ReactNode;
  /** Chips that move to a group of a long list. */
  jump?: ItemListJump;
  /** A note under the list, such as what the list leaves out. */
  foot?: React.ReactNode;
  /** The rows are a load order. The list is an ol and a row with `order` shows its number. */
  ordered?: boolean;
  className?: string;
}

function LockMark({ label }: { label: string }) {
  return (
    <span className="item-lock">
      <svg viewBox="0 0 12 14" width="11" height="13" aria-hidden="true" focusable="false">
        <rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor" />
        <path
          d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </svg>
      <span className="sr-only">{label}</span>
    </span>
  );
}

interface ItemRowProps {
  item: InspectorItem;
  selected: boolean;
  lockLabel: string;
  maskedLabel: string;
  notReadLabel: string;
  onOpen: ((id: string) => void) | undefined;
}

function ItemRow({ item, selected, lockLabel, maskedLabel, notReadLabel, onOpen }: ItemRowProps) {
  return (
    <li className="item-row" data-item-id={item.id}>
      <Link
        href={item.href}
        className={cx("item-link", selected && "chosen-row", item.className)}
        {...(selected ? { "aria-current": "page" as const } : {})}
        onPress={() => {
          onOpen?.(item.id);
        }}
      >
        <span className={cx("item-name", item.order !== undefined && "item-name-ordered")}>
          {item.order !== undefined && (
            <span className="item-order num" aria-hidden="true">
              {item.order}
            </span>
          )}
          <span className="item-name-text">
            {item.name}
            {item.locked === true && (
              <>
                {" "}
                <LockMark label={lockLabel} />
              </>
            )}
          </span>
        </span>
        {item.notRead === true ? (
          <span className="item-state item-not-read">
            <span className="item-not-read-mark" aria-hidden="true" />
            {notReadLabel}
          </span>
        ) : (
          item.status !== undefined && (
            <span className="item-state">
              <StatusChip status={item.status.status}>{item.status.label}</StatusChip>
            </span>
          )
        )}
        {item.value !== undefined && (
          <span className="item-value">
            <ValueText value={item.value} maskedLabel={maskedLabel} />
          </span>
        )}
      </Link>
    </li>
  );
}

/**
 * The list card of the list and inspector (components.md entry 26): a `nav` of React Aria Links in
 * a well, one URL per item. The picked item has the canonical chosen state, a --select-bg fill and
 * a 3 px --accent start bar, with `aria-current="page"`. Items are keyed by their stable id, so a
 * refetch changes values in place. A long list takes groups with headings and counts, and an empty
 * list shows one sentence and one action.
 */
export function ItemList({
  title,
  count,
  items,
  groups,
  selectedId,
  lockLabel,
  maskedLabel,
  notReadLabel,
  empty,
  onOpen,
  pre,
  jump,
  foot,
  ordered = false,
  className,
}: ItemListProps) {
  const List = ordered ? "ol" : "ul";
  const headingId = useId();
  const row = (item: InspectorItem) => (
    <ItemRow
      key={item.id}
      item={item}
      selected={item.id === selectedId}
      lockLabel={lockLabel}
      maskedLabel={maskedLabel}
      notReadLabel={notReadLabel}
      onOpen={onOpen}
    />
  );

  let body: React.ReactNode;
  if (items.length === 0 && empty !== undefined) {
    body = (
      <Well variant="flush">
        <EmptyState
          {...(empty.actionLabel !== undefined
            ? {
                action: {
                  label: empty.actionLabel,
                  ...(empty.href !== undefined ? { href: empty.href } : {}),
                  ...(empty.onPress !== undefined ? { onPress: empty.onPress } : {}),
                },
              }
            : {})}
        >
          {empty.text}
        </EmptyState>
      </Well>
    );
  } else if (groups !== undefined && groups.length > 0) {
    const known = new Set(groups.map((group) => group.key));
    const loose = items.filter((item) => item.group === undefined || !known.has(item.group));
    body = (
      <>
        {groups.map((group) => {
          const inGroup = items.filter((item) => item.group === group.key);
          if (inGroup.length === 0) return null;
          return (
            <section key={group.key} className="item-group" data-group={group.key}>
              {group.bare === true ? (
                <h3 className="sr-only" tabIndex={-1}>
                  {group.label}
                </h3>
              ) : (
                <h3 className="item-group-title" tabIndex={-1}>
                  {group.label} <span className="item-group-count num">{group.count}</span>
                </h3>
              )}
              <Well variant="list">
                <List className="item-ul">{inGroup.map(row)}</List>
                {group.more !== undefined && (
                  <div className="item-more">
                    <Button onPress={group.more.onPress}>{group.more.label}</Button>
                  </div>
                )}
              </Well>
            </section>
          );
        })}
        {loose.length > 0 && (
          <Well variant="list">
            <List className="item-ul">{loose.map(row)}</List>
          </Well>
        )}
      </>
    );
  } else {
    body = (
      <Well variant="list">
        <List className="item-ul">{items.map(row)}</List>
      </Well>
    );
  }

  return (
    <nav className={cx("card", "item-list", className)} aria-labelledby={headingId}>
      <header className="card-header">
        <h2 className="card-title" id={headingId}>
          {title}
        </h2>
        {count !== undefined && <span className="card-count num">{count}</span>}
      </header>
      <div className="card-body">
        {pre}
        {jump !== undefined && jump.chips.length > 0 && (
          <p className="item-jump">
            <span className="muted">{jump.label}</span>
            {jump.chips.map((chip) => (
              <button
                key={chip.key}
                type="button"
                className="item-jump-chip"
                onClick={chip.onPress}
              >
                {chip.label} <span className="num">{chip.count}</span>
              </button>
            ))}
          </p>
        )}
        {body}
        {foot !== undefined && <p className="item-foot muted">{foot}</p>}
      </div>
    </nav>
  );
}
