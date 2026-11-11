/*
 * A surface page, #/p/<project>/setup/<part> and #/p/<project>/setup/<part>/<item key>. One page
 * serves all ten parts: a list of the part's items on the left and the inspector of the picked item
 * on the right (components.md entry 26). The URL names the item, so the inspector follows the URL.
 *
 * Picking. At 1440 with no item in the URL the page shows the first item that needs a look, or else
 * the first item (owner decision 3). Opening an item moves focus to the inspector's h2. At 720px and
 * below the list is the page, and an item opens as its own page with a back link that returns focus
 * and scroll to the item in the list (owner decision 4, need 28).
 *
 * Long lists. A grouped list over 30 items shows six rows per group with Show n more, and Jump to
 * chips appear only then (owner decision 5). The picked item always shows.
 *
 * Editing. An edit route, `setup/<part>/<item key>/edit`, shows the same page. With edits on and an
 * item that has an editor, the editor takes the inspector's place beside the list, or is a full-height
 * sheet over the item on a phone. After Save it closes back to the inspector, which shows the Saved
 * box. With edits off the item shows with a note that takes focus. An item with no editor goes back
 * to its own page. A confirm for an undo of a changed file takes the inspector's place the same way.
 *
 * States. First load shows bones. A failed first read shows one raised error with Try again. A
 * refetch that fails keeps the last good list. A file that couldn't be read gets the Couldn't read
 * card over the partial list. An empty part says what would appear and offers its action. A picked
 * item that left the part shows the unknown-item sentence, and focus lands on its link (need 27).
 */
import { useEffect, useId, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router";
import { useProjects } from "@/api/client";
import { useEditRestart, useUndo } from "@/api/edit";
import { useProblems, useSetupMap, useSetupPart } from "@/api/setup";
import type { SetupItem, SetupPart, SetupPartAnswer } from "@/api/types";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { cx } from "@/components/cx";
import { ItemList } from "@/components/ListInspector/ItemList";
import type { ItemListEmpty, ItemListJump } from "@/components/ListInspector/ItemList";
import type { ListGroup } from "@/components/ListInspector/types";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { useIsDesktop } from "@/lib/media";
import { fieldOfItem } from "@/lib/edit-page";
import { listRow, planList, shapeGroups } from "@/lib/setup-list";
import {
  autoPickItem,
  itemId,
  itemKey,
  itemState,
  parseSetupRoute,
  setupItemPath,
  setupPartPath,
  setupPath,
} from "@/lib/setup-routes";
import type { SetupRoute } from "@/lib/setup-routes";
import { PART_EMPTY, PART_NAMES, PART_SUBS, groupLabel } from "@/lib/setup-words";
import { t, tn } from "@/strings/t";
import { CouldntReadCard, readFailures } from "./CouldntReadCard";
import { useEditAvailability } from "./edit-mode";
import { ItemInspector } from "./ItemInspector";
import { SettingsEditor } from "./SettingsEditor";
import type { SavedInfo } from "./SettingsEditor";
import { SetupBones, SetupError, SetupStale } from "./SetupStates";
import { UndoPanel, useUndoConfirm } from "./UndoPanel";
import type { UndoTarget } from "./UndoPanel";
import "./SurfacePage.css";

type PartRoute = Extract<SetupRoute, { part: SetupPart }>;

export function SurfacePage() {
  const { project } = useParams();
  const { pathname, search } = useLocation();
  if (project === undefined) return null;
  const route = parseSetupRoute(`${pathname}${search}`);
  if (route === null) return null;
  // A part name the server doesn't know has nothing to show, so the map is the way back.
  if (route.kind === "unknown_part") return <Navigate to={setupPath(project)} replace />;
  if (route.kind !== "part" && route.kind !== "item" && route.kind !== "edit") return null;
  return <SurfaceView key={`${project}:${route.part}`} project={project} route={route} />;
}

/** The row of an item in the list, by its id. The ids hold colons, so no selector is built. */
function rowOf(root: HTMLElement | null, id: string): HTMLElement | undefined {
  if (root === null) return undefined;
  return Array.from(root.querySelectorAll<HTMLElement>("[data-item-id]")).find(
    (el) => el.dataset.itemId === id,
  );
}

/** The unknown-item sentence, with a link back to the part. Focus lands on the link (need 27). */
function GoneCard({ part, href }: { part: SetupPart; href: string }) {
  const headingId = useId();
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.querySelector("a")?.focus();
  }, []);
  const name = PART_NAMES[part]();
  return (
    <section ref={ref} className="card setup-gone" aria-labelledby={headingId}>
      <h2 className="setup-gone-title" id={headingId}>
        {t("sp_gone_h", { part: name })}
      </h2>
      <p>{t("sp_gone_b")}</p>
      <div>
        <Button href={href}>{t("sp_back", { part: name })}</Button>
      </div>
    </section>
  );
}

function emptyOf(part: SetupPart, answer: SetupPartAnswer): ItemListEmpty {
  const info = answer.empty;
  if (info?.reason === "not_visible") return { text: t("em_nv") };
  const text = PART_EMPTY[part]();
  if (info?.action === "docs" && info.target !== null) {
    return { text, actionLabel: t("em_a_docs"), href: info.target };
  }
  if (info?.action === "copy_path" && info.target !== null) {
    const target = info.target;
    return {
      text,
      actionLabel: part === "instructions" ? t("em_a_copy_file") : t("em_a_copy_folder"),
      onPress: () => {
        void navigator.clipboard.writeText(target).then(
          () => {
            postStatus(t("an_copied"));
          },
          () => undefined,
        );
      },
    };
  }
  return { text };
}

function SurfaceView({ project, route }: { project: string; route: PartRoute }) {
  const { part, scopes } = route;
  const desktop = useIsDesktop();
  const card = useSetupPart(project, part);
  const problems = useProblems(project);
  const map = useSetupMap(project);
  const projects = useProjects();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const partName = PART_NAMES[part]();
  const answer = card.answer;
  const root = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const editHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set<string>());
  const revealed = useRef<string | null>(null);
  const lastItem = useRef<string | null>(null);

  // Editing. The saved box, the undo and the confirm outlive the rail, so they live here.
  const availability = useEditAvailability(project);
  const [saved, setSaved] = useState<SavedInfo | null>(null);
  const [undoTarget, setUndoTarget] = useState<UndoTarget | null>(null);
  const undo = useUndo(project);
  const confirm = useUndoConfirm(undo);

  const items: readonly SetupItem[] = answer?.items ?? [];
  const state = answer === undefined ? "none" : itemState(route, items);
  const onItem = route.kind === "item" || route.kind === "edit";
  let picked: SetupItem | null = null;
  if (onItem) {
    const id = itemId(part, route.key);
    picked = items.find((item) => item.id === id) ?? null;
  } else if (desktop && answer !== undefined) {
    picked = autoPickItem(items, problems.answer?.rows ?? []);
  }

  const mode = desktop ? "split" : onItem ? "inspector" : "list";
  const listed = answer !== undefined;
  const itemKeyNow = onItem ? route.key : null;
  const editField = picked === null ? null : fieldOfItem(picked);
  // A restart keeps the rail up even when the new server has editing off, because its box says why
  // Save can't go and names the command. The route note shows only when no rail is up.
  const restarted = useEditRestart() !== null;
  const editing =
    route.kind === "edit" && editField !== null && (availability.kind === "on" || restarted);

  // When the editor closes back to the item, focus goes to the inspector's heading.
  const lastKind = useRef(route.kind);
  useEffect(() => {
    if (lastKind.current === "edit" && route.kind === "item") headingRef.current?.focus();
    lastKind.current = route.kind;
  }, [route.kind]);

  // At 1440 the auto-picked item goes into the URL with replace, so a reload and Back keep it
  // and the pick adds no history entry.
  const navigate = useNavigate();
  const pickedKey = picked === null ? null : itemKey(part, picked.id);
  const autoPicked = route.kind === "part" && desktop;
  useEffect(() => {
    if (!autoPicked || pickedKey === null) return;
    void navigate(setupItemPath(project, part, pickedKey, scopes), { replace: true });
  }, [autoPicked, pickedKey, navigate, project, part, scopes]);

  // After Show n more the pressed button is gone, so focus moves to the first row it revealed.
  useEffect(() => {
    const id = revealed.current;
    if (id === null) return;
    revealed.current = null;
    rowOf(root.current, id)?.querySelector("a")?.focus();
  }, [expanded]);

  // On a phone, the back link returns to the list with focus and scroll on the item (need 28).
  useEffect(() => {
    if (itemKeyNow !== null) {
      lastItem.current = itemId(part, itemKeyNow);
      return;
    }
    if (desktop || !listed) {
      if (desktop) lastItem.current = null;
      return;
    }
    const id = lastItem.current;
    if (id === null) return;
    lastItem.current = null;
    const row = rowOf(root.current, id);
    if (row === undefined) return;
    row.querySelector("a")?.focus();
    row.scrollIntoView({ block: "center" });
  }, [itemKeyNow, desktop, listed, part]);

  const crumbs = {
    label: t("bc_label"),
    items: [
      { label: t("nav_setup"), href: `#${setupPath(project, scopes)}` },
      { label: partName, href: `#${setupPartPath(project, part, scopes)}` },
    ],
  };
  const header =
    mode === "inspector" ? (
      <h1 className="sr-only">{partName}</h1>
    ) : (
      <PageHeader title={partName} sub={PART_SUBS[part](projectName)} breadcrumb={crumbs} />
    );

  if (answer === undefined) {
    return (
      <div className="setup-page setup-surface" ref={root}>
        {header}
        <Card title={partName} className="setup-surface-card">
          {card.error === null ? (
            <SetupBones line={t("ld_line", { card: partName.toLowerCase() })} rows={6} />
          ) : (
            <SetupError card={partName} onRetry={card.retry} />
          )}
        </Card>
      </div>
    );
  }

  const shaped = shapeGroups(part, items, answer.groups);
  const groupKeys = shaped.groups.map((g) => g.key);
  const plan = planList(shaped.items, groupKeys, expanded, picked?.id);
  const groups: ListGroup[] = shaped.groups.map((g) => {
    const left = plan.hidden.get(g.key) ?? 0;
    return {
      key: g.key,
      label: groupLabel(part, g.key),
      count: String(g.count),
      ...(g.bare ? { bare: true } : {}),
      ...(left > 0
        ? {
            more: {
              label: tn("ss_more", left),
              onPress: () => {
                revealed.current = plan.firstHidden.get(g.key) ?? null;
                setExpanded((prev) => new Set(prev).add(g.key));
              },
            },
          }
        : {}),
    };
  });
  const jump: ItemListJump | undefined =
    plan.long && groups.length > 1
      ? {
          label: t("sp_jump"),
          chips: groups.map((g) => ({
            key: g.key,
            label: g.label,
            count: g.count,
            onPress: () => {
              const section = root.current?.querySelector<HTMLElement>(
                `[data-group="${g.key.replaceAll('"', "")}"]`,
              );
              const heading = section?.querySelector<HTMLElement>("h3");
              heading?.focus();
              section?.scrollIntoView({ block: "start" });
            },
          })),
        }
      : undefined;
  const failures = readFailures(answer.unreadable);

  const open = (): void => {
    queueMicrotask(() => {
      headingRef.current?.focus();
    });
  };
  const backHref = `#${setupPartPath(project, part, scopes)}`;
  // Cancel and Save both go back to the item, in place of the edit route, so Back skips the rail.
  // The effect above puts focus on the inspector's heading once the item is back.
  const closeRail = (): void => {
    if (itemKeyNow !== null)
      void navigate(setupItemPath(project, part, itemKeyNow, scopes), { replace: true });
  };
  const startUndo = (target: UndoTarget): void => {
    setUndoTarget(target);
    undo.undo(target.rowId, target.scope);
  };
  // Instruction files are a load order, so the list numbers them and says what it leaves out.
  const loadOrder = part === "instructions";

  // An edit route for an item with no editor, with edits on, is the item's own page. An agent's edit
  // route stays, because M6a edits no agents and the inspector says so in a note that takes focus.
  if (
    route.kind === "edit" &&
    picked !== null &&
    editField === null &&
    part !== "agents" &&
    availability.kind === "on"
  ) {
    return <Navigate to={setupItemPath(project, part, route.key, scopes)} replace />;
  }

  const inspector = picked !== null && (
    <ItemInspector
      item={picked}
      project={project}
      scopes={scopes}
      startedAt={map.answer?.server_started_at ?? null}
      inspector={{
        headingRef,
        ...(mode === "inspector" && !editing
          ? {
              focusOnMount: true,
              back: { label: partName, href: backHref },
            }
          : {}),
      }}
      edit={{ saved, undo, onUndo: startUndo, routeNote: route.kind === "edit" && !editing }}
    />
  );
  const confirming =
    confirm !== null && undoTarget !== null ? (
      <UndoPanel view={confirm} undo={undo} target={undoTarget} />
    ) : null;
  const editor =
    editing && picked !== null && editField !== null ? (
      <SettingsEditor
        key={picked.id}
        project={project}
        projectName={projectName}
        item={picked}
        field={editField}
        onCancel={closeRail}
        onSaved={(info) => {
          setSaved(info);
          closeRail();
        }}
        headingRef={editHeadingRef}
      />
    ) : null;

  let right: React.ReactNode = null;
  if (picked !== null) {
    // At 721px and up the editor or the undo confirm takes the inspector's place. On a phone they
    // are sheets over the item.
    right = (
      <>
        {desktop && (editor !== null || confirming !== null) ? null : inspector}
        {editor}
        {confirming}
      </>
    );
  } else if (state === "vanished") {
    right = <GoneCard part={part} href={backHref} />;
  }

  return (
    <div className="setup-page setup-surface" data-part={part} ref={root}>
      {header}
      {card.failed && <SetupStale receivedAt={card.receivedAt} />}
      <div
        className={cx("list-inspector", mode !== "split" && "list-inspector-single")}
        data-mode={mode}
      >
        {mode !== "inspector" && (
          <ItemList
            title={partName}
            count={String(items.length)}
            items={plan.shown.map((item, index) => ({
              ...listRow(project, item, scopes),
              ...(loadOrder ? { order: index + 1 } : {}),
            }))}
            groups={groups}
            ordered={loadOrder}
            {...(loadOrder ? { foot: t("ins_memory") } : {})}
            {...(picked !== null ? { selectedId: picked.id } : {})}
            lockLabel={t("in_lock_word")}
            maskedLabel={t("in_masked_word")}
            notReadLabel={t("su_nr")}
            empty={emptyOf(part, answer)}
            {...(failures.length > 0 ? { pre: <CouldntReadCard files={failures} /> } : {})}
            {...(jump !== undefined ? { jump } : {})}
            onOpen={open}
          />
        )}
        {mode !== "list" && right}
      </div>
    </div>
  );
}
