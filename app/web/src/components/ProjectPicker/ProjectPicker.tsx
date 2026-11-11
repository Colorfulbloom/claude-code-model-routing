import { Dialog, Modal, ModalOverlay } from "react-aria-components";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { HelpButton } from "../HelpButton/HelpButton";
import { SelectList, type SelectOption } from "../Select/Select";
import "./ProjectPicker.css";

export const states = ["open", "empty", "loading"] as const;

/** How a project reads in the list. Every kind shows a glyph and its words, never hue alone. */
export type ProjectKind = "ready" | "working" | "idle" | "bad";

export interface ProjectItem {
  id: string;
  name: string;
  /** The display path, in mono. */
  path: string;
  kind: ProjectKind;
  /** The state word, such as "Ready" or "Folder not found". */
  stateWord: string;
  /** What opening it gives, for the two states that need a line. */
  detail?: string;
}

const glyphs: Record<ProjectKind, string> = {
  ready: "✓",
  working: "●",
  idle: "○",
  bad: "✕",
};

/** One project as a listbox option, shared by the sidebar Select and the picker list. */
export function projectOption(item: ProjectItem): SelectOption {
  return {
    id: item.id,
    label: item.name,
    description: (
      <>
        <span className="pk-path" title={item.path}>
          {item.path}
        </span>
        <span className={cx("pk-state", `pk-state-${item.kind}`)}>
          <span aria-hidden="true">{glyphs[item.kind]}</span>
          {item.stateWord}
        </span>
        {item.detail !== undefined && <span className="pk-detail">{item.detail}</span>}
      </>
    ),
  };
}

/** The empty state of the picker: a heading and one sentence, with no command row. */
export function ProjectsEmpty({ title, body }: { title: string; body: string }) {
  return (
    <div className="pk-empty">
      <p className="pk-empty-title">{title}</p>
      <p className="muted">{body}</p>
    </div>
  );
}

export interface ProjectPickerProps {
  /** The heading, "Projects". */
  heading: string;
  items: ProjectItem[];
  value: string | null;
  onChange: (id: string) => void;
  /** The heading level. The picker page makes it the page h1, everywhere else it is an h2. */
  headingLevel?: 1 | 2;
  /** Shows Close in the header. The tray passes it, the page does not. */
  closeLabel?: string;
  onClose?: () => void;
  emptyTitle: string;
  emptyBody: string;
  loadingText: string;
  /** True until the first project list arrives. */
  loading?: boolean;
  /** Moves focus into the list on mount. */
  focusOnMount?: boolean;
  className?: string;
}

/** The picker content: a header, then one option per project or the empty state (components.md entry 51). */
export function ProjectPicker({
  heading,
  headingLevel = 2,
  items,
  value,
  onChange,
  closeLabel,
  onClose,
  emptyTitle,
  emptyBody,
  loadingText,
  loading = false,
  focusOnMount = false,
  className,
}: ProjectPickerProps) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <section className={cx("pk", className)}>
      <header className="pk-head">
        <div className="pk-title">
          <Heading className="pk-heading">{heading}</Heading>
          <HelpButton help="shell.projectstate" />
        </div>
        {closeLabel !== undefined && onClose !== undefined && (
          <Button variant="icon" ariaLabel={closeLabel} onPress={onClose} className="pk-close">
            {"✕"}
          </Button>
        )}
      </header>
      {loading ? (
        <p className="pk-note muted" role="status">
          {loadingText}
        </p>
      ) : items.length === 0 ? (
        <ProjectsEmpty title={emptyTitle} body={emptyBody} />
      ) : (
        <SelectList
          items={items.map(projectOption)}
          aria-label={heading}
          selectedKeys={value === null ? [] : [value]}
          onChange={onChange}
          {...(focusOnMount ? { autoFocus: true } : {})}
          className="pk-list"
        />
      )}
    </section>
  );
}

export interface ProjectTrayProps extends Omit<
  ProjectPickerProps,
  "closeLabel" | "onClose" | "focusOnMount"
> {
  /** The Close button's accessible name. The tray always has one, the route sheet only when it can go back. */
  closeLabel?: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** "tray" is the bottom sheet, "sheet" is a centred modal for 721px and up. */
  layout?: "tray" | "sheet";
  /** False keeps the modal open on Esc and a scrim click. */
  dismissable?: boolean;
  /** Moves focus to the list on open. The route sheet leaves focus to the route harness. */
  focusOnMount?: boolean;
  /** The Dialog element, so the route harness can find the h1 in it. */
  dialogRef?: React.Ref<HTMLElement>;
}

/**
 * The picker as a modal over a real scrim element that covers the top bar and tab bar. The tray
 * is a bottom sheet at 720px and below. The sheet layout is a centred card at 721px and up. Esc
 * and the scrim close it. The caller returns focus to the trigger, because the trigger is the top
 * bar button.
 */
export function ProjectTray({
  isOpen,
  onOpenChange,
  layout = "tray",
  dismissable = true,
  focusOnMount = true,
  dialogRef,
  closeLabel,
  ...picker
}: ProjectTrayProps) {
  return (
    <ModalOverlay
      className="pk-scrim"
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      isDismissable={dismissable}
      isKeyboardDismissDisabled={!dismissable}
    >
      <Modal className={layout === "sheet" ? "pk-sheet" : "pk-tray"}>
        <Dialog
          className="pk-dialog"
          aria-label={picker.heading}
          {...(dialogRef ? { ref: dialogRef } : {})}
        >
          <ProjectPicker
            {...picker}
            focusOnMount={focusOnMount}
            {...(closeLabel !== undefined ? { closeLabel } : {})}
            onClose={() => {
              onOpenChange(false);
            }}
          />
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
