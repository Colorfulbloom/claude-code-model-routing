import type { ReactNode } from "react";
import { Button, type ButtonVariant } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { CommandRow } from "@/components/CommandRow/CommandRow";
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { GatePage } from "@/components/GatePage/GatePage";
import { ModelSwatch, type Model } from "@/components/ModelSwatch/ModelSwatch";
import { MoreCard } from "@/components/MoreCard/MoreCard";
import { NewTabLine } from "@/components/NewTabLine/NewTabLine";
import { NoticeLine } from "@/components/NoticeLine/NoticeLine";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { ProjectPicker, type ProjectItem } from "@/components/ProjectPicker/ProjectPicker";
import { ProgressSteps, type ProgressStep } from "@/components/ProgressSteps/ProgressSteps";
import { RaisedFinding, type RaisedFindingVariant } from "@/components/RaisedFinding/RaisedFinding";
import { RetryRow } from "@/components/RetryRow/RetryRow";
import { RunStateGlyph, type RunState } from "@/components/RunStateGlyph/RunStateGlyph";
import { HistoryCard } from "@/components/HistoryCard/HistoryCard";
import { Sidebar, type SidebarGroup } from "@/components/Sidebar/Sidebar";
import { SidebarFooter } from "@/components/SidebarFooter/SidebarFooter";
import { StoppedNotice } from "@/components/StoppedNotice/StoppedNotice";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { TabBar, type TabBarItem } from "@/components/TabBar/TabBar";
import { TopBar } from "@/components/TopBar/TopBar";
import { WaitHold } from "@/components/WaitHold/WaitHold";
import { Well } from "@/components/Well/Well";
import { FirstRunContent, LockedContent } from "@/pages/GatePages";
import { projectItem } from "@/lib/projects";
import { t, tn } from "@/strings/t";
import { SelectDemo } from "./SelectDemo";
import { W } from "./words";

function footerSample(problem: boolean) {
  return [
    ...(problem ? [{ id: "unreadable", text: tn("ft_unreadable", 3), warn: true as const }] : []),
    { id: "updated", text: t("ft_updated", { t: "6:41 PM" }) },
    { id: "since", text: t("ft_since", { d: "September 3" }) },
    problem
      ? { id: "backup", text: t("ft_backup_failed", { t: "4:02 AM" }), warn: true as const }
      : { id: "backup", text: t("ft_backup", { t: "4:02 AM" }) },
    { id: "prices", text: t("ft_prices", { d: "October 28" }) },
    { id: "claude", text: t("more_ver_cc", { version: "2.1.310" }) },
  ];
}

function historySampleRows(problem: boolean) {
  return [
    { id: "updated", label: t("more_l_updated"), value: "6:41 PM" },
    { id: "since", label: t("more_l_since"), value: "September 3" },
    problem
      ? {
          id: "backup",
          label: t("more_l_backup"),
          value: t("ft_backup_failed", { t: "4:02 AM" }),
          warn: true as const,
        }
      : { id: "backup", label: t("more_l_backup"), value: "4:02 AM" },
    { id: "prices", label: t("more_l_prices"), value: "October 28" },
  ];
}

/** One rendered state of one component. `component` is the folder name under src/components. */
export interface ManifestEntry {
  component: string;
  state: string;
  render: () => ReactNode;
}

const variants: { variant: ButtonVariant; label: string }[] = [
  { variant: "primary", label: W.ed_save },
  { variant: "secondary", label: W.in_copy },
  { variant: "quiet", label: W.ed_cancel },
  { variant: "danger", label: W.rk_go },
  { variant: "icon", label: "✕" },
];

function buttons(state: string): ReactNode {
  return (
    <div className="sheet-wrap">
      {variants.map(({ variant, label }) => {
        const iconProps = variant === "icon" ? { ariaLabel: W.ed_close } : {};
        const forced =
          state === "hover"
            ? "is-hover"
            : state === "focus"
              ? "is-focus"
              : state === "pressed"
                ? "is-pressed"
                : "";
        const stateProps =
          state === "disabled"
            ? { disabled: true, disabledReason: W.rk_note }
            : state === "busy"
              ? { busy: true, busyLabel: W.cs_saving }
              : {};
        return (
          <Button key={variant} variant={variant} className={forced} {...iconProps} {...stateProps}>
            {label}
          </Button>
        );
      })}
    </div>
  );
}

const navGroups = (
  force: "hover" | "focus" | null,
  endSlot: boolean,
  current: boolean,
): SidebarGroup[] => [
  {
    id: "live",
    items: [
      {
        id: "live",
        href: "#live",
        label: W.nav_live,
        icon: "live",
        current,
        ...(endSlot ? { end: <RunStateGlyph state="working">{W.nav_working}</RunStateGlyph> } : {}),
      },
    ],
  },
  {
    id: "review",
    heading: W.nav_review,
    items: [
      {
        id: "summary",
        href: "#summary",
        label: W.nav_summary,
        icon: "summary",
        ...(force === "hover" ? { className: "is-hover" } : {}),
      },
      {
        id: "sessions",
        href: "#sessions",
        label: W.nav_sessions,
        icon: "sessions",
        ...(force === "focus" ? { className: "is-focus" } : {}),
      },
    ],
  },
  {
    id: "setup",
    heading: W.nav_setup_h,
    items: [
      { id: "setup", href: "#setup", label: W.nav_setup, icon: "setup" },
      {
        id: "tofix",
        href: "#tofix",
        label: W.nav_tofix,
        icon: "tofix",
        ...(endSlot ? { end: W.tofix_count } : {}),
      },
    ],
  },
];

function sidebar(force: "hover" | "focus" | null, endSlot = false, current = false): ReactNode {
  return (
    <div className="sheet-sidebar">
      <Sidebar
        label={W.sheet_nav_label}
        brand={W.sheet_brand}
        groups={navGroups(force, endSlot, current)}
        footer={W.sheet_version}
      />
    </div>
  );
}

const tabItems = (
  force: "hover" | "focus" | null,
  count: boolean,
  current: boolean,
): TabBarItem[] => [
  { id: "live", href: "#live", label: W.nav_live, icon: "live", current },
  {
    id: "review",
    href: "#review",
    label: W.nav_review,
    icon: "review",
    ...(force === "hover" ? { className: "is-hover" } : {}),
  },
  {
    id: "setup",
    href: "#setup",
    label: W.nav_setup_h,
    icon: "setup",
    ...(force === "focus" ? { className: "is-focus" } : {}),
  },
  {
    id: "tofix",
    href: "#tofix",
    label: W.nav_tofix,
    icon: "tofix",
    ...(count ? { count: W.tofix_count, name: `${W.nav_tofix}, ${W.tofix_count}` } : {}),
  },
  { id: "more", href: "#more", label: W.nav_more, icon: "more" },
];

function tabBar(force: "hover" | "focus" | null, count = false, current = false): ReactNode {
  return (
    <div className="sheet-phone">
      <TabBar label={W.sheet_tabs_label} items={tabItems(force, count, current)} />
    </div>
  );
}

const topProject = (open: boolean) => ({
  name: W.project_name,
  label: t("project_aria", { name: W.project_name }),
  open,
  onPress: () => undefined,
});

const projectRows: ProjectItem[] = [
  { id: "tidewater", name: W.project_name, path: "~/work/tidewater-reporting", running: true },
  { id: "driftwood", name: "Driftwood", path: "~/work/driftwood", running: false },
  { id: "saltmarsh", name: "Saltmarsh", path: "~/work/saltmarsh", running: false },
  { id: "harbor", name: "Harbor notes", path: "~/work/old/harbor-notes", running: false },
].map((row, index) =>
  projectItem({
    key: row.id,
    name: row.name,
    display_path: row.path,
    running: row.running,
    state: index === 2 ? "no_claude_folder" : index === 3 ? "folder_not_found" : "ok",
  }),
);

const picker = (empty: boolean, loading: boolean): ReactNode => (
  <ProjectPicker
    heading={t("pk_h")}
    items={empty ? [] : projectRows}
    value="tidewater"
    onChange={() => undefined}
    closeLabel={t("pk_close")}
    onClose={() => undefined}
    emptyTitle={t("pk_empty_h")}
    emptyBody={t("pk_empty")}
    loadingText={t("pk_loading")}
    loading={loading}
  />
);

const sampleCommand = "/bartab";
const sampleRoute = "/p/builder/review/agents";

const crumb = {
  label: W.sheet_crumb_label,
  items: [
    { label: W.nav_setup, href: "#setup" },
    { label: "Effort", href: "#effort" },
  ],
};

const findingWords: Record<
  RaisedFindingVariant,
  { title?: string; body: string; actions?: ReactNode }
> = {
  plain: { body: W.rv_chk_sum },
  check: { title: W.cs_v_check, body: W.rv_chk_q },
  warning: { title: W.ed_warn_h, body: W.ed_warn },
  overwritten: {
    body: W.ed_over,
    actions: (
      <>
        <Button variant="primary">{W.ed_review_changes}</Button>
        <Button>{W.ed_undo}</Button>
      </>
    ),
  },
  saved: { title: W.ed_saved, body: W.ed_saved_meta, actions: <Button>{W.ed_undo}</Button> },
  error: { body: W.cs_prev_err, actions: <Button>{W.cs_prev_err_a}</Button> },
};

const runWords: Record<RunState, string> = {
  working: W.st_working,
  done: W.st_done,
  idle: W.st_idle,
  failed: W.fr_failed,
};

const models: { model: Model; name: string }[] = [
  { model: "opus", name: W.m_opus },
  { model: "sonnet", name: W.m_sonnet },
  { model: "haiku", name: W.m_haiku },
  { model: "fable", name: W.m_fable },
];

const stepFor = (state: "done" | "current" | "next" | "failed"): ProgressStep => {
  const base = { id: state, state } as const;
  switch (state) {
    case "done":
      return { ...base, name: W.fr_s1, stateWord: W.fr_done };
    case "current":
      return {
        ...base,
        name: W.fr_s2,
        stateWord: W.fr_now,
        progress: { percent: 50, text: W.fr_progress },
      };
    case "next":
      return { ...base, name: W.fr_s3, stateWord: W.fr_next };
    case "failed":
      return { ...base, name: W.fr_s3, stateWord: W.fr_failed };
  }
};

/** Every component in every state. The test beside this file fails when one is missing. */
export const manifest: ManifestEntry[] = [
  // Sidebar
  { component: "Sidebar", state: "default", render: () => sidebar(null) },
  { component: "Sidebar", state: "hover", render: () => sidebar("hover") },
  { component: "Sidebar", state: "focus", render: () => sidebar("focus") },
  { component: "Sidebar", state: "selected", render: () => sidebar(null, false, true) },
  { component: "Sidebar", state: "end-slot", render: () => sidebar(null, true) },
  // TabBar
  { component: "TabBar", state: "default", render: () => tabBar(null) },
  { component: "TabBar", state: "hover", render: () => tabBar("hover") },
  { component: "TabBar", state: "focus", render: () => tabBar("focus") },
  { component: "TabBar", state: "selected", render: () => tabBar(null, false, true) },
  { component: "TabBar", state: "count", render: () => tabBar(null, true) },
  // TopBar
  {
    component: "TopBar",
    state: "default",
    render: () => (
      <div className="sheet-phone">
        <TopBar title={W.nav_summary} />
      </div>
    ),
  },
  {
    component: "TopBar",
    state: "with-project",
    render: () => (
      <div className="sheet-phone">
        <TopBar title={W.nav_summary} project={topProject(false)} />
      </div>
    ),
  },
  {
    component: "TopBar",
    state: "project-open",
    render: () => (
      <div className="sheet-phone">
        <TopBar title={W.nav_summary} project={topProject(true)} />
      </div>
    ),
  },
  // PageHeader
  {
    component: "PageHeader",
    state: "default",
    render: () => <PageHeader title={W.su_h1} sub={W.su_sub} />,
  },
  {
    component: "PageHeader",
    state: "with-controls",
    render: () => (
      <PageHeader
        title={W.su_h1}
        sub={W.su_sub}
        controls={
          <SelectDemo
            label={W.rv_range_lab}
            items={[
              { id: "30", label: W.rv_range },
              { id: "90", label: "Last 90 days" },
            ]}
            initial="30"
          />
        }
      />
    ),
  },
  {
    component: "PageHeader",
    state: "with-breadcrumb",
    render: () => <PageHeader title="Effort" sub={W.su_sub} breadcrumb={crumb} />,
  },
  // Card
  {
    component: "Card",
    state: "default",
    render: () => <Card title={W.rv_chk_h}>{W.rv_chk_sum}</Card>,
  },
  {
    component: "Card",
    state: "header-extras",
    render: () => (
      <Card
        title={W.rv_chk_h}
        count="3"
        question={W.rv_chk_q}
        right={<Button variant="quiet">{W.cs_tb_empty_a}</Button>}
      >
        {W.rv_chk_sum}
      </Card>
    ),
  },
  {
    component: "Card",
    state: "foot",
    render: () => (
      <Card title={W.rv_chk_h} foot={W.ed_saved_meta}>
        {W.rv_chk_sum}
      </Card>
    ),
  },
  // Well
  { component: "Well", state: "default", render: () => <Well>{W.rv_chk_sum}</Well> },
  {
    component: "Well",
    state: "list",
    render: () => (
      <Well variant="list">
        <p className="sheet-row">{W.nav_agents}</p>
        <p className="sheet-row">{W.nav_models}</p>
      </Well>
    ),
  },
  {
    component: "Well",
    state: "flush",
    render: () => <Well variant="flush">{W.rv_chk_sum}</Well>,
  },
  // RaisedFinding
  ...(Object.keys(findingWords) as RaisedFindingVariant[]).map((variant) => ({
    component: "RaisedFinding",
    state: variant,
    render: () => {
      const words = findingWords[variant];
      return (
        <RaisedFinding
          variant={variant}
          {...(words.title !== undefined ? { title: words.title } : {})}
          {...(words.actions !== undefined ? { actions: words.actions } : {})}
        >
          {words.body}
        </RaisedFinding>
      );
    },
  })),
  // NoticeLine
  {
    component: "NoticeLine",
    state: "default",
    render: () => <NoticeLine statusWord={W.st_unknown}>{W.su_version}</NoticeLine>,
  },
  {
    component: "NoticeLine",
    state: "with-link",
    render: () => (
      <NoticeLine statusWord={W.st_unknown} link={{ label: W.su_version_link, href: "#decides" }}>
        {W.su_version}
      </NoticeLine>
    ),
  },
  // Button
  ...["default", "hover", "focus", "pressed", "disabled", "busy"].map((state) => ({
    component: "Button",
    state,
    render: () => buttons(state),
  })),
  // Select
  ...(["default", "hover", "focus", "open", "disabled"] as const).map((state) => ({
    component: "Select",
    state,
    render: () => (
      <SelectDemo
        label={W.rv_range_lab}
        items={[
          { id: "7", label: "Last 7 days" },
          { id: "30", label: W.rv_range, description: W.cs_s_default },
          { id: "90", label: "Last 90 days" },
        ]}
        initial="30"
        state={state}
      />
    ),
  })),
  // EmptyState
  {
    component: "EmptyState",
    state: "page",
    render: () => (
      <EmptyState
        variant="page"
        title={W.fx_empty_h}
        action={{ label: W.fx_empty_a, href: "#setup" }}
      >
        {W.fx_empty}
      </EmptyState>
    ),
  },
  {
    component: "EmptyState",
    state: "page-neutral",
    render: () => (
      <EmptyState variant="page" mark="neutral">
        {t("ph_body")}
      </EmptyState>
    ),
  },
  {
    component: "EmptyState",
    state: "inline",
    render: () => (
      <Well>
        <EmptyState action={{ label: W.cs_list_empty_a }}>{W.cs_list_empty}</EmptyState>
      </Well>
    ),
  },
  // ProgressSteps
  ...(
    [
      ["done", ["done", "current", "next"]],
      ["in-progress", ["done", "current", "next"]],
      ["next", ["done", "current", "next"]],
      ["failed", ["done", "failed"]],
    ] as const
  ).map(([state, steps]) => ({
    component: "ProgressSteps",
    state,
    render: () => <ProgressSteps label={W.sheet_steps_label} steps={steps.map(stepFor)} />,
  })),
  // GatePage
  {
    component: "GatePage",
    state: "default",
    render: () => (
      <div className="sheet-gate">
        <GatePage brand={W.sheet_brand}>
          <h1 className="gate-title">{W.lk_h}</h1>
          <p className="muted">{W.lk_body}</p>
          <Well>
            <code>{W.lk_cmd}</code>
          </Well>
          <div>
            <Button>{W.lk_copy}</Button>
          </div>
        </GatePage>
      </div>
    ),
  },
  // The gate: four locked reasons and first run failed, on the same markup the real pages use
  ...(
    [
      ["locked-no-key", "no_key"],
      ["locked-code-used", "code_used"],
      ["locked-code-expired", "code_expired"],
      ["locked-server-restarted", "server_restarted"],
    ] as const
  ).map(([state, reason]) => ({
    component: "GatePage",
    state,
    render: () => (
      <div className="sheet-gate">
        <GatePage brand={t("product")}>
          <LockedContent reason={reason} command={sampleCommand} route={sampleRoute} />
        </GatePage>
      </div>
    ),
  })),
  {
    component: "GatePage",
    state: "first-run-failed",
    render: () => (
      <div className="sheet-gate">
        <GatePage brand={t("product")}>
          <FirstRunContent
            command={sampleCommand}
            ingest={{
              state: "failed",
              files_done: 640,
              files_total: 1240,
              bytes_done: 800_000_000,
              bytes_total: 2_000_000_000,
              retrying: false,
              retry_at: "2026-11-08T23:14:00Z",
              error: { code: "config_dir_unreadable", file: "~/.claude/projects/tidewater" },
            }}
          />
        </GatePage>
      </div>
    ),
  },
  // SidebarFooter
  {
    component: "SidebarFooter",
    state: "default",
    render: () => (
      <div className="sheet-sidebar">
        <SidebarFooter lines={footerSample(false)} />
      </div>
    ),
  },
  {
    component: "SidebarFooter",
    state: "problem",
    render: () => (
      <div className="sheet-sidebar">
        <SidebarFooter lines={footerSample(true)} />
      </div>
    ),
  },
  // StoppedNotice
  {
    component: "StoppedNotice",
    state: "default",
    render: () => (
      <StoppedNotice>
        {t("nt_stopped_config_dir_unreadable", { t: "6:12 PM", f: "/work/.claude/projects" })}
      </StoppedNotice>
    ),
  },
  // HistoryCard
  {
    component: "HistoryCard",
    state: "default",
    render: () => (
      <div className="sheet-phone">
        <HistoryCard title={t("more_hist_h")} rows={historySampleRows(false)} />
      </div>
    ),
  },
  {
    component: "HistoryCard",
    state: "problem",
    render: () => (
      <div className="sheet-phone">
        <HistoryCard
          title={t("more_hist_h")}
          findings={[
            {
              id: "backup",
              title: t("ft_backup_failed", { t: "4:02 AM" }),
              body: t("mb_backup_no_space"),
            },
            {
              id: "unreadable",
              title: tn("ft_unreadable", 3),
              body: t("mb_unread_b"),
            },
          ]}
          rows={historySampleRows(true)}
        />
      </div>
    ),
  },
  // CommandRow
  ...(["default", "copied"] as const).map((state) => ({
    component: "CommandRow",
    state,
    render: () => (
      <CommandRow
        primary
        command={sampleCommand}
        copyLabel={t("lk_copy")}
        copiedLabel={t("cs_copied")}
        copied={state === "copied"}
      />
    ),
  })),
  // RetryRow
  ...(["default", "loading"] as const).map((state) => ({
    component: "RetryRow",
    state,
    render: () => (
      <RetryRow
        retryText={t("st_retry")}
        lastText={t("st_last", { time: "3:42 PM" })}
        tryLabel={t("stopped_try_now")}
        busyLabel={t("st_trying")}
        busy={state === "loading"}
        onTryNow={() => undefined}
      />
    ),
  })),
  // NewTabLine
  {
    component: "NewTabLine",
    state: "default",
    render: () => (
      <NewTabLine>{t("lk_tab_back", { page: W.nav_agents, project: "builder" })}</NewTabLine>
    ),
  },
  // WaitHold
  {
    component: "WaitHold",
    state: "default",
    render: () => (
      <div className="sheet-wait">
        <WaitHold brand={t("product")} status={t("hold_status")} />
      </div>
    ),
  },
  // ProjectPicker
  { component: "ProjectPicker", state: "open", render: () => picker(false, false) },
  { component: "ProjectPicker", state: "empty", render: () => picker(true, false) },
  { component: "ProjectPicker", state: "loading", render: () => picker(false, true) },
  // MoreCard
  ...(["default", "focus"] as const).map((state) => ({
    component: "MoreCard",
    state,
    render: () => (
      <MoreCard
        title={W.nav_ref_h}
        rows={[
          {
            id: "decides",
            href: "#decides",
            label: W.nav_decides,
            icon: "decides" as const,
            ...(state === "focus" ? { className: "is-focus" } : {}),
          },
          { id: "glossary", href: "#glossary", label: W.nav_glossary, icon: "glossary" as const },
        ]}
      />
    ),
  })),
  // ModelSwatch
  ...models.map(({ model, name }) => ({
    component: "ModelSwatch",
    state: model,
    render: () => (
      <span className="sheet-model">
        <ModelSwatch model={model} />
        <b>{name}</b>
      </span>
    ),
  })),
  // SkeletonBones
  {
    component: "SkeletonBones",
    state: "text",
    render: () => (
      <SkeletonBones label={W.cs_tb_loading} bones={[{ width: "l" }, { width: "m" }]} />
    ),
  },
  {
    component: "SkeletonBones",
    state: "value",
    render: () => (
      <SkeletonBones
        label={W.cs_tb_loading}
        bones={[{ width: "s", height: "value" }, { width: "m" }]}
      />
    ),
  },
  {
    component: "SkeletonBones",
    state: "rows",
    render: () => (
      <Well aria-busy="true">
        <SkeletonBones
          label={W.cs_tb_loading}
          bones={[{ width: "full" }, { width: "full" }, { width: "full" }]}
        />
      </Well>
    ),
  },
  // RunStateGlyph
  ...(Object.keys(runWords) as RunState[]).map((state) => ({
    component: "RunStateGlyph",
    state,
    render: () => <RunStateGlyph state={state}>{runWords[state]}</RunStateGlyph>,
  })),
  // Chosen state (a shared standard in shared.css, not a component folder)
  {
    component: "ChosenState",
    state: "edge",
    render: () => (
      <div className="sheet-wrap">
        <span className="sheet-choice chosen chosen-mark">{W.sheet_chosen_edge}</span>
        <span className="sheet-choice">{W.sheet_unchosen}</span>
      </div>
    ),
  },
  {
    component: "ChosenState",
    state: "focus",
    render: () => (
      <span className="sheet-choice chosen chosen-mark is-focus">{W.sheet_chosen_edge}</span>
    ),
  },
  {
    component: "ChosenState",
    state: "row",
    render: () => (
      <span className="sheet-choice chosen-row">
        <span className="chosen-word">
          {"✓ "}
          {W.sheet_chosen_word}
        </span>{" "}
        {W.sheet_chosen_row}
      </span>
    ),
  },
];
