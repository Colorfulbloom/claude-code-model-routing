/*
 * The confirm for undoing a save when the file changed since (plan 5.3, designer item 22). The undo
 * answers `changed_since_save` with what Undo would change, and this panel shows that and asks.
 * `useUndoConfirm` keeps the answer on screen while "Undo anyway" is in flight, so the panel
 * doesn't flash away and back. The inspector shows it in place of the item (a sheet on a phone),
 * and the Changes page shows it inline under the row.
 */
import { useEffect, useRef, useState } from "react";
import { Dialog, Modal, ModalOverlay } from "react-aria-components";
import type { EditScope, UndoHandle, UndoPreview } from "@/api/edit";
import { UndoConfirm } from "@/components/UndoConfirm/UndoConfirm";
import { useIsDesktop } from "@/lib/media";
import { t } from "@/strings/t";
import { fileNameOf } from "./edit-mode";
import "./UndoPanel.css";

/** What the confirm is about: the row and the file it changes. */
export interface UndoTarget {
  rowId: string;
  /** The scope of the row, or null when the page doesn't know it (an undo reaches every project). */
  scope: EditScope | null;
  displayPath: string;
  /** The real file when the display path is a link, else null. */
  realPath: string | null;
  /**
   * The real file's whole path, "~" for home, where the page can build it. The confirm of an undo
   * that deletes the file names it, so the person sees exactly what goes.
   */
  fullPath?: string;
}

export interface UndoConfirmView {
  rowId: string;
  preview: UndoPreview;
  /** "Undo anyway" is in flight. */
  busy: boolean;
}

/** The confirm to show now, or null. It holds the last answer while the confirmed undo is sent. */
export function useUndoConfirm(undo: UndoHandle): UndoConfirmView | null {
  const { state } = undo;
  const [held, setHeld] = useState<{ rowId: string; preview: UndoPreview } | null>(null);
  if (state.kind === "conflict" && held?.preview.version !== state.undoPreview.version) {
    setHeld({ rowId: state.rowId, preview: state.undoPreview });
  } else if ((state.kind === "idle" || state.kind === "done") && held !== null) {
    setHeld(null);
  }
  if (state.kind === "conflict") {
    return { rowId: state.rowId, preview: state.undoPreview, busy: false };
  }
  if (state.kind === "sending" && held !== null && held.rowId === state.rowId) {
    return { ...held, busy: true };
  }
  return null;
}

export interface DeleteUndoPanelProps {
  target: UndoTarget;
  /** The undo is in flight. */
  busy: boolean;
  onKeep: () => void;
  onAnyway: () => void;
}

/**
 * The confirm under a Changes row whose undo deletes the file Bar Tab made (undo state
 * `deletes_file`). The server undoes such a row at once, with no preview to confirm, so this panel
 * asks first, in the same frame as the others, and sends the undo only on "Undo anyway". It names
 * the real file it deletes by its whole path, "~" for home, and under a link it keeps the link's
 * own path above that. It has no lines of its own to show, because the server sends none for it.
 */
export function DeleteUndoPanel({ target, busy, onKeep, onAnyway }: DeleteUndoPanelProps) {
  const desktop = useIsDesktop();
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);
  const real = target.fullPath ?? target.realPath ?? target.displayPath;
  const linked = target.realPath !== null;
  return (
    <div className="setup-undo-inline">
      <UndoConfirm
        file={fileNameOf(target.displayPath)}
        path={linked ? target.displayPath : real}
        {...(linked ? { linksTo: real } : {})}
        warning={t("cg_deletes_file")}
        onKeep={onKeep}
        onAnyway={onAnyway}
        busy={busy}
        anywayFirst={!desktop}
        headingRef={headingRef}
      />
    </div>
  );
}

export interface UndoPanelProps {
  view: UndoConfirmView;
  undo: UndoHandle;
  target: UndoTarget;
  /** Inline under a Changes row. The inspector's panel sits in a card, or a sheet on a phone. */
  inline?: boolean;
}

/** The confirm, with focus on its heading. */
export function UndoPanel({ view, undo, target, inline = false }: UndoPanelProps) {
  const desktop = useIsDesktop();
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);
  const sheet = !inline && !desktop;
  const confirm = (
    <UndoConfirm
      file={fileNameOf(target.displayPath)}
      path={target.displayPath}
      {...(target.realPath !== null ? { linksTo: target.realPath } : {})}
      lines={view.preview.diff.lines}
      onKeep={undo.reset}
      onAnyway={undo.undoAnyway}
      busy={view.busy}
      layout={sheet ? "sheet" : "panel"}
      // Under a Changes row on a phone the buttons stack with "Undo anyway" first, as the sheet does.
      anywayFirst={inline && !desktop}
      headingRef={headingRef}
    />
  );
  if (inline) return <div className="setup-undo-inline">{confirm}</div>;
  if (!sheet) return <section className="card setup-undo-card">{confirm}</section>;
  return (
    <ModalOverlay
      className="edit-rail-scrim"
      isOpen
      isDismissable={!view.busy}
      isKeyboardDismissDisabled={view.busy}
      onOpenChange={(open) => {
        if (!open) undo.reset();
      }}
    >
      <Modal className="edit-rail-modal">
        <Dialog aria-label={t("ed_undo_h")} className="setup-undo-sheet">
          {confirm}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
