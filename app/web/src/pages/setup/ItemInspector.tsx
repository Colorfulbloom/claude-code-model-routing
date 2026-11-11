/*
 * The inspector of one item (components.md entry 26) filled from a SetupItem. The headline says what
 * runs, then where it is set (top wins), why and how sure Bar Tab is. A read-only item gets the
 * read-only box with its owner's reason, the command to copy or Copy path. An item the server did
 * not read gets a box under the headline with the Unknown pill. Copy path copies the full local path
 * while the screen shows the short one (owner answer, November 9).
 *
 * Editing. A Settings item with an editor gets an Edit button at the foot of the inspector. With
 * edits on it opens the edit route. With edits off it stays in place, aria-disabled and focusable,
 * and one visible line under it says why and names the command (plan 5.2). A save made on this page
 * shows its Saved box at the top (`ItemEditStatus`). An edit route opened with edits off shows the
 * item with a note that takes focus.
 *
 * An agent adds three things. A callout under the headline when it doesn't run as its file sets it,
 * a run line with the cost over 30 days from /api/agents, and the footer link to the Agents page in
 * Review. Its where-set well lists its own files only (`whereRows`).
 */
import { useEffect, useId, useRef } from "react";
import { useAgents } from "@/api/review";
import { useRules } from "@/api/rules";
import type { SetupItem } from "@/api/types";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { CopyPath } from "@/components/CopyPath/CopyPath";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { Inspector } from "@/components/ListInspector/Inspector";
import type { InspectorProps } from "@/components/ListInspector/Inspector";
import { agentCheckView } from "@/lib/agent-check";
import { agentUsageLine, showReviewLink } from "@/lib/agent-usage";
import { editPathOf, fieldOfItem, fieldWord } from "@/lib/edit-page";
import { reviewPath } from "@/lib/range";
import { itemName } from "@/lib/setup-list";
import { changesPath, itemKey, setupItemPath } from "@/lib/setup-routes";
import {
  appliesLine,
  copyPathOf,
  hasMaskedValue,
  notReadView,
  notYetEditableView,
  readOnlyView,
  runsLine,
  setLine,
  statusOf,
  usageLine,
  whereRows,
  whyView,
} from "@/lib/setup-inspector";
import type { ReadOnlyView } from "@/lib/setup-inspector";
import { decidesHref } from "@/pages/reference/reference-routes";
import { ruleTarget } from "@/pages/reference/rules-view";
import { t } from "@/strings/t";
import { EditsOffNote } from "@/components/EditsOffNote/EditsOffNote";
import { AgentCallout } from "./AgentCallout";
import { useEditAvailability } from "./edit-mode";
import type { EditAvailability } from "./edit-mode";
import { InspectorFacts } from "./InspectorFacts";
import { ItemEditStatus } from "./ItemEditStatus";
import type { SavedInfo } from "./SettingsEditor";
import type { UndoTarget } from "./UndoPanel";
import type { UndoHandle } from "@/api/edit";

/** What an inspector needs to show a save, an undo and an edit route's note. */
export interface ItemEditProps {
  /** The save made on this page, for the Saved and Overwritten boxes. */
  saved: SavedInfo | null;
  undo: UndoHandle;
  onUndo: (target: UndoTarget) => void;
  /** The edit route opened this page. With edits off the note above the item takes focus. */
  routeNote: boolean;
}

export interface ItemInspectorProps {
  edit?: ItemEditProps;
  item: SetupItem;
  project: string;
  /** The Switch's state, which the links inside the inspector keep. */
  scopes: boolean;
  /** `server_started_at`, which dates the shell scope. */
  startedAt: string | null;
  /** The ListInspector's heading ref and phone props, passed through. */
  inspector?: Pick<InspectorProps, "headingRef" | "focusOnMount" | "back">;
}

const ID_MARK = "⁣";

/** "See the rule {id}" with the id in the code font. The arrow is drawn after it. */
function ruleLinkLabel(id: string): React.ReactNode {
  const [before = "", after = ""] = t("in_rule_link", { id: ID_MARK }).split(ID_MARK);
  return (
    <>
      {before}
      <code className="mono setup-rule-id">{id}</code>
      {after}
    </>
  );
}

/**
 * The lock box of an item that has an editor where edits can't be turned on: a demo or sample run,
 * or a project whose folder is missing. The owner can't enable editing from there, so the box
 * replaces the Edit button. A missing folder also offers Copy path.
 */
function unavailableView(availability: EditAvailability): ReadOnlyView | null {
  if (availability.kind === "demo") {
    return { lockLabel: t("ro_h"), reason: t("eo_reason_demo") };
  }
  if (availability.kind === "folder") {
    return {
      lockLabel: t("ro_h"),
      reason: t("eo_reason_folder", { path: availability.path }),
      path: { value: availability.path, label: t("in_copy"), copiedLabel: t("an_copied") },
    };
  }
  return null;
}

/** The inspector of one item. An agent's also reads its runs and cost over 30 days. */
export function ItemInspector(props: ItemInspectorProps) {
  return props.item.part === "agents" ? (
    <AgentItemInspector {...props} />
  ) : (
    <ItemInspectorView {...props} />
  );
}

function AgentItemInspector(props: ItemInspectorProps) {
  const agents = useAgents(props.project, "30d");
  return (
    <ItemInspectorView
      {...props}
      agentUsage={agentUsageLine(props.item, agents.answer, "30d")}
      reviewLink={showReviewLink(props.item, agents.answer)}
    />
  );
}

interface ItemInspectorViewProps extends ItemInspectorProps {
  /** An agent's run line with cost, or null while the Agents answer loads. */
  agentUsage?: string | null;
  /** False hides the Review link, for a plugin or managed agent with no runs. */
  reviewLink?: boolean;
}

function ItemInspectorView({
  item,
  project,
  scopes,
  startedAt,
  inspector,
  edit,
  agentUsage = null,
  reviewLink = true,
}: ItemInspectorViewProps) {
  const runs = runsLine(item);
  const setTo = setLine(item);
  const field = fieldOfItem(item);
  const availability = useEditAvailability(project);
  const noteId = useId();
  const routeRef = useRef<HTMLDivElement>(null);
  // An agent's edit URL always gets the note, because M6a edits no agents. Any other edit URL gets
  // it when edits are off or unavailable.
  const agentRoute = edit?.routeNote === true && item.part === "agents";
  const showRouteNote =
    agentRoute ||
    (edit?.routeNote === true && availability.kind !== "on" && availability.kind !== "loading");
  useEffect(() => {
    if (showRouteNote) routeRef.current?.focus();
  }, [showRouteNote]);
  // Where edits can't be turned on from here (a demo, a missing folder), an editable item shows the
  // lock box with its reason in place of an Edit button the owner can't enable. The route note
  // says the same thing, so the box waits while the note shows.
  const unavailable = field !== null && !showRouteNote ? unavailableView(availability) : null;
  const readOnly = readOnlyView(item) ?? notYetEditableView(item) ?? unavailable;
  const notRead = notReadView(item);
  const where = whereRows(item, startedAt);
  const why = whyView(item);
  // The rule behind the reason, for the Why line's link and its older-version mark.
  const rules = useRules();
  const rule = ruleTarget(item.reason?.rule_id, rules.answer);
  // The agent's run line with cost replaces the server's runs-only line once /api/agents answers.
  const usage = agentUsage ?? usageLine(item);
  const applies = appliesLine(item);
  const path = copyPathOf(item);
  const masked = hasMaskedValue(item);
  const check = agentCheckView(item);
  const agentKey = item.part === "agents" ? itemKey("agents", item.id) : null;
  const copy =
    readOnly === null && path !== null ? (
      <CopyPath
        value={path}
        label={t("in_copy")}
        copiedLabel={t("an_copied")}
        onStatus={postStatus}
      />
    ) : null;
  const agentsLink =
    agentKey === null || !reviewLink ? null : (
      <Button
        variant="quiet"
        className="setup-agents-link"
        href={`#${reviewPath(project, "agents", "30d", { agent: agentKey })}`}
      >
        {t("ag_runs_link", { name: itemName(item) })} <span aria-hidden="true">→</span>
      </Button>
    );
  // Edit stays in the foot. With edits on it is a link. Otherwise it is aria-disabled and focusable,
  // with one visible reason under it, tied to it by aria-describedby.
  const key = itemKey(item.part, item.id);
  const editHref =
    field !== null && key !== null
      ? `#${editPathOf(setupItemPath(project, item.part, key, scopes))}`
      : null;
  const editName = field === null ? undefined : t("ed_edit_aria", { field: fieldWord(field) });
  const editButton =
    field === null ||
    availability.kind === "loading" ||
    availability.kind === "demo" ||
    availability.kind === "folder" ? null : availability.kind === "on" ? (
      editHref === null ? null : (
        <Button
          variant="primary"
          href={editHref}
          {...(editName !== undefined ? { ariaLabel: editName } : {})}
        >
          {t("ed_edit")}
        </Button>
      )
    ) : (
      <Button
        disabled
        describedBy={noteId}
        {...(editName !== undefined ? { ariaLabel: editName } : {})}
      >
        {t("ed_edit")}
      </Button>
    );
  // The reason under a disabled Edit. While the route note shows, it says the same, so it waits.
  const editReason =
    field === null || showRouteNote || availability.kind !== "off" ? null : (
      <div className="setup-edit-reason">
        <EditsOffNote id={noteId} kind="reason" command={availability.command} />
      </div>
    );
  const routeNote = !showRouteNote ? null : agentRoute ? (
    <EditsOffNote id={noteId} kind="agent" name={itemName(item)} noteRef={routeRef} />
  ) : availability.kind === "off" ? (
    <EditsOffNote
      id={noteId}
      kind="route"
      item={itemName(item)}
      command={availability.command}
      noteRef={routeRef}
    />
  ) : availability.kind === "folder" ? (
    <div ref={routeRef} tabIndex={-1} className="setup-edit-route">
      <EditsOffNote kind="folder" path={availability.path} />
    </div>
  ) : (
    <div ref={routeRef} tabIndex={-1} className="setup-edit-route">
      <EditsOffNote kind="demo" />
    </div>
  );
  const status =
    edit !== undefined && field !== null ? (
      <ItemEditStatus
        key={item.id}
        project={project}
        item={item}
        field={field}
        saved={edit.saved}
        undo={edit.undo}
        onUndo={edit.onUndo}
        changesHref={`#${changesPath(project)}`}
      />
    ) : null;
  const parts: InspectorProps = {
    title: itemName(item),
    status: statusOf(item),
    ...(inspector ?? {}),
    ...(routeNote !== null || status !== null
      ? {
          finding: (
            <>
              {routeNote}
              {status}
            </>
          ),
        }
      : {}),
    ...(runs !== null
      ? {
          runs: (
            <>
              {runs.text}
              {runs.masked && <span className="setup-runs-mask muted"> {t("in_masked_word")}</span>}
            </>
          ),
        }
      : {}),
    ...(setTo !== null ? { setTo } : {}),
    ...(readOnly !== null
      ? {
          readOnly: {
            lockLabel: readOnly.lockLabel,
            reason: readOnly.reason,
            ...(readOnly.command !== undefined ? { command: readOnly.command } : {}),
            ...(readOnly.path !== undefined ? { path: readOnly.path } : {}),
          },
        }
      : {}),
    ...(notRead !== null ? { notRead: { status: statusOf(item), body: notRead.body } } : {}),
    ...(check !== null ? { check: <AgentCallout view={check} /> } : {}),
    details: <InspectorFacts item={item} project={project} scopes={scopes} />,
    ...(where.length > 0
      ? { where: { title: t("in_where_h"), rows: where, maskedLabel: t("in_masked_word") } }
      : {}),
    ...(why !== null
      ? {
          why: {
            title: t("in_why_h"),
            body: why.body,
            confidence: why.confidence,
            ...(rule === null
              ? {}
              : {
                  ...(rule.due && rule.installed !== null
                    ? { older: t("in_older", { installed: rule.installed }) }
                    : {}),
                  link: {
                    label: ruleLinkLabel(rule.id),
                    href: decidesHref({ setting: rule.key, rule: rule.id }),
                  },
                }),
          },
        }
      : {}),
    ...(usage !== null ? { usage } : {}),
    ...(editButton !== null || copy !== null || agentsLink !== null
      ? {
          actions: (
            <>
              {editButton}
              {copy}
              {agentsLink}
              {editReason}
            </>
          ),
        }
      : {}),
  };
  return (
    <Inspector {...parts}>
      {item.real_path !== null && (
        <p className="inspector-small muted setup-link">
          <span aria-hidden="true">{"↪"}</span> {t("in_link", { path: item.real_path })}
        </p>
      )}
      {item.may_change && <p className="inspector-small muted">{t("in_may_change")}</p>}
      {where.some((r) => r.id.startsWith("shell")) && (
        <p className="inspector-small muted">{t("in_shell_note")}</p>
      )}
      {applies !== null && (
        <p className="inspector-small muted">
          <HelpTerm help="setup.applies">{applies}</HelpTerm>
        </p>
      )}
      {masked && <p className="inspector-small muted">{t("in_masked")}</p>}
    </Inspector>
  );
}
