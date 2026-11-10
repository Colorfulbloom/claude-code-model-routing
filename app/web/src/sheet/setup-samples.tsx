/*
 * Sample data for the setup components on the component sheet (wave 4): the breadcrumb, the switch,
 * scope labels and chips, the list and inspector, and the To fix rows and groups. Every word comes
 * from words.ts (sheet-only words) or the string deck, and every value is made up for the sheet.
 * Nothing here is real data.
 */
import { useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb/Breadcrumb";
import { CopyPath } from "@/components/CopyPath/CopyPath";
import {
  Inspector,
  ListInspector,
  type InspectorItem,
  type InspectorProps,
  type ListGroup,
  type ListInspectorProps,
  type ScopeRow,
  type StatusWord,
} from "@/components/ListInspector/ListInspector";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { ScopeChip } from "@/components/ScopeChip/ScopeChip";
import { ScopeLabel } from "@/components/ScopeLabel/ScopeLabel";
import type { SettingStatus } from "@/components/StatusChip/StatusChip";
import { Switch } from "@/components/Switch/Switch";
import { ToFixGroup, type ToFixKind } from "@/components/ToFixGroup/ToFixGroup";
import { ToFixRow, type ToFixRowProps } from "@/components/ToFixRow/ToFixRow";
import { t } from "@/strings/t";
import { W } from "./words";

const statusWords: Record<SettingStatus, string> = {
  in_effect: W.st_in_effect,
  overridden: W.st_overridden,
  ignored: W.st_ignored,
  lowered: W.st_lowered,
  invalid: W.st_invalid,
  default: W.st_default,
  unknown: W.st_unknown,
};

const word = (status: SettingStatus): StatusWord => ({ status, label: statusWords[status] });

/* ---------- Breadcrumb ---------- */

export type BreadcrumbState = "default" | "hover" | "focus" | "long" | "hidden";

export function BreadcrumbDemo({ state }: { state: BreadcrumbState }) {
  const items = [
    { label: W.nav_setup, href: "#setup" },
    { label: W.sp_list_h, href: "#settings" },
    { label: state === "long" ? W.sheet_crumb_long : W.sp_effort, href: "#effort" },
  ].map((item, i) =>
    i === 0 && state === "hover"
      ? { ...item, className: "is-hover" }
      : i === 0 && state === "focus"
        ? { ...item, className: "is-focus" }
        : item,
  );
  const trail = (
    <Breadcrumb label={W.sheet_crumb_label} items={items} hidden={state === "hidden"} />
  );
  if (state === "long") return <div className="sheet-phone sheet-pad">{trail}</div>;
  if (state === "hidden") {
    return (
      <div className="sheet-wrap">
        {trail}
        <p className="muted">{W.sheet_hidden_note}</p>
      </div>
    );
  }
  return trail;
}

/* ---------- Switch ---------- */

export type SwitchState = "off" | "on" | "hover" | "focus" | "disabled-off" | "disabled-on";

/** A switch that holds its own state on the sheet, so it can be toggled. */
export function SwitchDemo({ state }: { state: SwitchState }) {
  const [on, setOn] = useState(state === "on" || state === "disabled-on");
  const disabled = state === "disabled-off" || state === "disabled-on";
  return (
    <Switch
      selected={on}
      onChange={setOn}
      disabled={disabled}
      disabledReason={W.sheet_switch_reason}
      {...(state === "hover" ? { className: "is-hover" } : {})}
      {...(state === "focus" ? { className: "is-focus" } : {})}
    >
      {W.su_switch}
    </Switch>
  );
}

/* ---------- Scope label and chip ---------- */

export const scopeNames = [
  { name: W.sc_managed, meaning: W.sc_managed_2 },
  { name: W.sc_cli, meaning: W.sc_cli_2 },
  { name: W.sc_local, meaning: W.sc_local_2 },
  { name: W.sc_project, meaning: W.sc_project_2 },
  { name: W.sc_user, meaning: W.sc_user_2 },
  { name: W.sc_plugin, meaning: W.sc_plugin_2 },
  { name: W.sc_shell, meaning: W.sc_shell_2 },
];

export function ScopeLabelDemo({ long }: { long: boolean }) {
  if (long) {
    return (
      <div className="sheet-narrow">
        <ScopeLabel
          name={W.sc_project}
          meaning={`${W.sc_project_2}, ${W.sc_user_2}, ${W.sc_cli_2}`}
        />
      </div>
    );
  }
  return (
    <div className="sheet-wrap">
      {scopeNames.slice(0, 4).map((scope) => (
        <ScopeLabel key={scope.name} name={scope.name} meaning={scope.meaning} />
      ))}
    </div>
  );
}

export function ScopeChipDemo({ state }: { state: "default" | "wrap" | "truncated" }) {
  if (state === "wrap") {
    return (
      <div className="sheet-phone sheet-pad">
        <div className="sheet-wrap">
          <ScopeChip scope={W.sc_local} value={W.sp_v_effort} />
          <ScopeChip scope={W.sc_project} value={W.sheet_scope_long_value} />
        </div>
      </div>
    );
  }
  if (state === "truncated") {
    return (
      <div className="sheet-phone sheet-pad">
        <ScopeChip scope={W.sc_plugin} value={W.sheet_scope_plugin_name} truncate />
      </div>
    );
  }
  return (
    <div className="sheet-wrap">
      <ScopeChip scope={W.sc_local} value={W.sp_v_effort} />
      <ScopeChip scope={W.sc_user} value={W.sp_v_model} />
      <ScopeChip scope={W.sc_managed} value={W.sp_v_allowed} />
    </div>
  );
}

/* ---------- Copy path ---------- */

export function CopyPathDemo({ copied }: { copied: boolean }) {
  return (
    <CopyPath
      value={W.sheet_path_user}
      label={W.in_copy}
      copiedLabel={t("cs_copied")}
      copied={copied}
    />
  );
}

/* ---------- List and inspector ---------- */

export type ListInspectorState =
  | "list"
  | "hover"
  | "focus"
  | "selected"
  | "selected-focus"
  | "read-only"
  | "not-read"
  | "unknown"
  | "couldnt-read"
  | "masked"
  | "empty"
  | "grouped"
  | "long-values"
  | "phone-list"
  | "phone-inspector";

const settingRows: { key: string; name: string; value: string; status: SettingStatus }[] = [
  { key: "model", name: W.sp_model, value: W.sp_v_model, status: "in_effect" },
  { key: "effort", name: W.sp_effort, value: W.sp_v_effort, status: "lowered" },
  { key: "cap", name: W.sp_cap, value: W.sp_v_cap, status: "in_effect" },
  { key: "think", name: W.sp_think, value: W.sp_v_think, status: "default" },
  { key: "compact", name: W.sp_compact, value: W.sp_v_compact, status: "default" },
  { key: "cache", name: W.sp_cache, value: W.sp_v_cache, status: "unknown" },
  { key: "fallback", name: W.sp_fallback, value: W.sp_v_fallback, status: "default" },
  { key: "allowed", name: W.sp_allowed, value: W.sp_v_allowed, status: "in_effect" },
];

function settingItems(force?: { id: string; className: string }): InspectorItem[] {
  return settingRows.map((row) => ({
    id: `settings:${row.key}`,
    name: row.name,
    href: `#setting-${row.key}`,
    value: { text: row.value },
    status: word(row.status),
    ...(row.key === "allowed" ? { locked: true } : {}),
    ...(force?.id === `settings:${row.key}` ? { className: force.className } : {}),
  }));
}

const baseList = (items: InspectorItem[], selectedId?: string): ListInspectorProps["list"] => ({
  title: W.sp_list_h,
  count: String(items.length),
  items,
  ...(selectedId !== undefined ? { selectedId } : {}),
  lockLabel: W.sheet_lock_word,
  maskedLabel: W.sheet_masked_word,
  notReadLabel: W.sheet_not_read,
});

const effortWhere: ScopeRow[] = [
  {
    id: "local",
    scope: { name: W.sc_local, meaning: W.sc_local_2 },
    key: "env.CLAUDE_CODE_EFFORT_LEVEL",
    value: { text: "xhigh" },
    status: word("lowered"),
    location: W.sheet_where_local,
  },
  {
    id: "project",
    scope: { name: W.sc_project, meaning: W.sc_project_2 },
    key: "effortLevel",
    value: { text: "medium" },
    status: word("overridden"),
    location: W.sheet_where_project,
  },
  {
    id: "user",
    scope: { name: W.sc_user, meaning: W.sc_user_2 },
    key: "effortLevel",
    value: { text: "xhigh" },
    status: word("ignored"),
    location: W.sheet_where_user,
  },
  {
    id: "shell",
    scope: { name: W.sc_shell, meaning: W.sc_shell_2 },
    key: "CLAUDE_CODE_EFFORT_LEVEL",
    note: W.su_nv,
  },
  {
    id: "cli",
    scope: { name: W.sc_cli, meaning: W.sc_cli_2 },
    key: "--effort",
    note: W.su_nv,
  },
];

const effortInspector: NonNullable<ListInspectorProps["inspector"]> = {
  title: W.sp_effort,
  status: word("lowered"),
  runs: W.in_runs,
  setTo: W.in_set,
  where: { title: W.in_where_h, rows: effortWhere, maskedLabel: W.sheet_masked_word },
  why: { title: W.in_why_h, body: W.in_why, confidence: W.in_conf },
  usage: W.in_usage,
  actions: <CopyPath value={W.sheet_path_user} label={W.in_copy} copiedLabel={t("cs_copied")} />,
};

const readOnlyInspector: NonNullable<ListInspectorProps["inspector"]> = {
  title: W.sp_allowed,
  status: word("in_effect"),
  runs: W.ro_runs,
  setTo: W.ro_set,
  readOnly: {
    lockLabel: W.sheet_lock_word,
    reason: W.ro_reason,
    command: {
      command: W.sheet_cmd_remove,
      copyLabel: W.lk_copy,
      copiedLabel: t("cs_copied"),
    },
    path: { value: W.sheet_path_managed, label: W.in_copy, copiedLabel: t("cs_copied") },
  },
  where: {
    title: W.in_where_h,
    maskedLabel: W.sheet_masked_word,
    rows: [
      {
        id: "managed",
        scope: { name: W.sc_managed, meaning: W.sc_managed_2 },
        key: "availableModels",
        value: { text: W.sp_v_allowed },
        status: word("in_effect"),
        location: W.sheet_where_managed,
      },
      {
        id: "user",
        scope: { name: W.sc_user, meaning: W.sc_user_2 },
        key: "availableModels",
        note: W.su_nv,
        status: word("default"),
      },
    ],
  },
};

const maskedInspector: NonNullable<ListInspectorProps["inspector"]> = {
  title: W.sheet_item_secret,
  status: word("in_effect"),
  runs: W.sheet_item_secret_value,
  where: {
    title: W.in_where_h,
    maskedLabel: W.sheet_masked_word,
    rows: [
      {
        id: "user",
        scope: { name: W.sc_user, meaning: W.sc_user_2 },
        key: "env.API_KEY",
        value: { text: W.sheet_item_secret_value, masked: true },
        status: word("in_effect"),
        location: W.sheet_where_user,
      },
    ],
  },
};

const maskedItem: InspectorItem = {
  id: "mcp:docs-search",
  name: W.sheet_item_secret,
  href: "#mcp-docs-search",
  value: { text: W.sheet_item_secret_value, masked: true },
  status: word("in_effect"),
};

const notReadItem: InspectorItem = {
  id: "instructions:other",
  name: W.sheet_item_not_read,
  href: "#instructions-other",
  notRead: true,
};

const phoneBack = { label: W.sheet_back_settings, href: "#settings" };

function withInspector(
  inspector: ListInspectorProps["inspector"],
  extra: Partial<ListInspectorProps> = {},
): Omit<ListInspectorProps, "list"> {
  return { inspector, ...extra };
}

/** One state of the list and inspector, built from sample data. */
export function ListInspectorDemo({ state }: { state: ListInspectorState }) {
  switch (state) {
    case "list":
      return <ListInspector list={baseList(settingItems())} {...withInspector(null)} />;
    case "hover":
      return (
        <ListInspector
          list={baseList(settingItems({ id: "settings:cap", className: "is-hover" }))}
          {...withInspector(null)}
        />
      );
    case "focus":
      return (
        <ListInspector
          list={baseList(settingItems({ id: "settings:cap", className: "is-focus" }))}
          {...withInspector(null)}
        />
      );
    case "selected":
      return (
        <ListInspector
          list={baseList(settingItems(), "settings:effort")}
          {...withInspector(effortInspector)}
        />
      );
    case "selected-focus":
      return (
        <ListInspector
          list={baseList(
            settingItems({ id: "settings:effort", className: "is-focus" }),
            "settings:effort",
          )}
          {...withInspector(effortInspector)}
        />
      );
    case "read-only":
      return (
        <ListInspector
          list={baseList(settingItems(), "settings:allowed")}
          {...withInspector(readOnlyInspector)}
        />
      );
    case "not-read":
      return (
        <ListInspector
          list={baseList([...settingItems().slice(0, 3), notReadItem], notReadItem.id)}
          {...withInspector({
            title: W.sheet_item_not_read,
            notRead: { status: word("unknown"), body: W.sheet_not_read_why },
          })}
        />
      );
    case "unknown":
      return (
        <ListInspector
          list={baseList(settingItems(), "settings:cache")}
          {...withInspector({
            title: W.sp_cache,
            status: word("unknown"),
            runs: W.sp_v_cache,
            where: {
              title: W.in_where_h,
              maskedLabel: W.sheet_masked_word,
              rows: [
                {
                  id: "user",
                  scope: { name: W.sc_user, meaning: W.sc_user_2 },
                  key: "cacheLifetime",
                  note: W.su_nv,
                },
              ],
            },
          })}
        />
      );
    case "couldnt-read":
      return (
        <ListInspector
          list={baseList(settingItems(), "settings:cap")}
          {...withInspector({
            title: W.sp_cap,
            status: word("in_effect"),
            finding: (
              <RaisedFinding variant="error" title={W.sheet_unreadable_title}>
                <p>{W.sheet_unreadable_body}</p>
              </RaisedFinding>
            ),
            runs: W.sp_v_cap,
          })}
        />
      );
    case "masked":
      return (
        <ListInspector
          list={baseList([maskedItem, ...settingItems().slice(0, 2)], maskedItem.id)}
          {...withInspector(maskedInspector)}
        />
      );
    case "empty":
      return (
        <ListInspector
          list={{
            ...baseList([]),
            title: W.sp_list_h,
            count: "0",
            empty: { text: W.sheet_empty_hooks, actionLabel: W.sheet_empty_action, href: "#docs" },
          }}
          {...withInspector(null)}
        />
      );
    case "grouped": {
      const groups: ListGroup[] = [
        { key: "allow", label: W.sheet_group_allow, count: "3" },
        { key: "deny", label: W.sheet_group_deny, count: "2" },
      ];
      const grouped = settingItems()
        .slice(0, 5)
        .map((item, i) => ({
          ...item,
          group: i < 3 ? "allow" : "deny",
        }));
      return (
        <ListInspector
          list={{ ...baseList(grouped, "settings:model"), groups }}
          {...withInspector(effortInspector)}
        />
      );
    }
    case "long-values": {
      const longItems: InspectorItem[] = [
        {
          id: "settings:long",
          name: W.sheet_item_long,
          href: "#setting-long",
          value: { text: W.sheet_item_long_value },
          status: word("overridden"),
        },
        {
          id: "settings:long-lock",
          name: W.sp_allowed,
          href: "#setting-long-lock",
          value: { text: W.sheet_scope_long_value },
          status: word("in_effect"),
          locked: true,
        },
      ];
      return (
        <div className="sheet-phone">
          <ListInspector
            mode="list"
            list={baseList(longItems, "settings:long")}
            {...withInspector(null)}
          />
        </div>
      );
    }
    case "phone-list":
      return (
        <div className="sheet-phone">
          <ListInspector mode="list" list={baseList(settingItems())} {...withInspector(null)} />
        </div>
      );
    case "phone-inspector": {
      const props: InspectorProps = { ...effortInspector, back: phoneBack };
      return (
        <div className="sheet-phone">
          <Inspector {...props} />
        </div>
      );
    }
  }
}

/* ---------- To fix ---------- */

export type ToFixRowState =
  "open-item" | "copy-command" | "copy-path" | "cant-fix-here" | "couldnt-read" | "long";

const rowBase = {
  open: {
    title: W.fx_r2_t,
    cause: W.fx_r2_c,
    location: ".mcp.json:8",
    consequence: W.fx_r2_q,
  },
  read: {
    title: W.fx_r1_t,
    cause: W.fx_r1_c,
    consequence: W.fx_r1_q,
  },
  effort: {
    title: W.fx_r3_t,
    cause: W.fx_r3_c,
    consequence: W.fx_r3_q,
  },
  unknown: {
    title: W.fx_r5_t,
    cause: W.fx_r5_c,
    consequence: W.fx_r5_q,
  },
} satisfies Record<string, Omit<ToFixRowProps, "action">>;

function rowProps(state: ToFixRowState): ToFixRowProps {
  switch (state) {
    case "open-item":
      return {
        ...rowBase.open,
        action: { kind: "open_item", label: W.fx_r2_a, href: "#mcp-docs-search" },
      };
    case "copy-command":
      return {
        ...rowBase.open,
        action: {
          kind: "copy_command",
          command: W.sheet_cmd_remove,
          copyLabel: W.lk_copy,
          copiedLabel: t("cs_copied"),
        },
      };
    case "copy-path":
      return {
        ...rowBase.read,
        action: {
          kind: "copy_path",
          path: W.sheet_path_user,
          label: W.fx_r1_a,
          copiedLabel: t("cs_copied"),
          ariaLabel: W.sheet_copy_path_named,
        },
      };
    case "cant-fix-here":
      return { ...rowBase.effort, action: { kind: "cant_fix_here", reason: W.ro_reason } };
    case "couldnt-read":
      return {
        ...rowBase.read,
        unreadable: true,
        action: {
          kind: "copy_path",
          path: W.sheet_path_user,
          label: W.fx_r1_a,
          copiedLabel: t("cs_copied"),
          ariaLabel: W.sheet_copy_path_named,
        },
      };
    case "long":
      return {
        title: W.sheet_tofix_long_title,
        cause: W.sheet_tofix_long_cause,
        location: "a-very-long-agent-file-name.md:12",
        consequence: W.fx_r1_q,
        action: { kind: "cant_fix_here", reason: W.ro_reason },
      };
  }
}

/** One To fix row, in its list, as it sits in a group. */
export function ToFixRowDemo({ state }: { state: ToFixRowState }) {
  return (
    <ul className="sheet-list">
      <ToFixRow {...rowProps(state)} />
    </ul>
  );
}

export type ToFixGroupState = "couldnt-read" | "wont-load" | "not-as-set" | "cant-tell" | "notices";

const groupKinds: Record<ToFixGroupState, ToFixKind> = {
  "couldnt-read": "couldnt_read",
  "wont-load": "wont_load",
  "not-as-set": "not_as_set",
  "cant-tell": "cant_tell",
  notices: "notices",
};

/** One To fix group card with its rows. */
export function ToFixGroupDemo({ state }: { state: ToFixGroupState }) {
  const kind = groupKinds[state];
  switch (state) {
    case "couldnt-read":
      return (
        <ToFixGroup kind={kind} title={W.fx_g_read} count="1">
          <ToFixRow {...rowProps("couldnt-read")} />
        </ToFixGroup>
      );
    case "wont-load":
      return (
        <ToFixGroup kind={kind} title={W.fx_g_load} count="1">
          <ToFixRow {...rowProps("open-item")} />
        </ToFixGroup>
      );
    case "not-as-set":
      return (
        <ToFixGroup kind={kind} title={W.fx_g_notset} count="2">
          <ToFixRow
            {...rowBase.effort}
            action={{ kind: "open_item", label: W.fx_r3_a, href: "#setting-effort" }}
          />
          <ToFixRow {...rowProps("cant-fix-here")} />
        </ToFixGroup>
      );
    case "cant-tell":
      return (
        <ToFixGroup kind={kind} title={W.fx_g_cant} note={W.fx_g_cant_note}>
          <ToFixRow
            {...rowBase.unknown}
            action={{ kind: "cant_fix_here", reason: W.sheet_cant_tell_reason }}
          />
        </ToFixGroup>
      );
    case "notices":
      return (
        <ToFixGroup kind={kind} title={W.fx_notes_h} note={W.fx_notes_q}>
          <li>{W.fx_n2}</li>
          <li>{W.su_version}</li>
        </ToFixGroup>
      );
  }
}
