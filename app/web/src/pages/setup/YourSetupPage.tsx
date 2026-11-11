/*
 * Your setup, #/p/<project>/setup. One card, "What shapes a session", with a row for each of the ten
 * parts: what applies, and the statuses of its items. A part row opens that part's list and
 * inspector. The Switch "Show where each comes from" keeps its state in `?scopes=1` and puts one
 * scope chip under each row for every scope that has something to say (owner decision 1). Every
 * row carries its scopes already, so the Switch fetches nothing and focus stays on it.
 *
 * States. First load shows bones with one spoken line. A failed first read shows one raised error
 * with Try again. A refetch that fails keeps the last good rows and says so. A project that is not
 * on Bar Tab's list reads "Not read here" in its project scopes, with a notice. A part that is empty
 * or that Bar Tab can't see keeps its row.
 */
import { useParams, useSearchParams } from "react-router";
import { useProjects } from "@/api/client";
import { useRules } from "@/api/rules";
import type { RulesCard } from "@/api/rules";
import { useSetupMap } from "@/api/setup";
import type { SetupMap } from "@/api/types";
import { Card } from "@/components/Card/Card";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { NoticeLine } from "@/components/NoticeLine/NoticeLine";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { ScopeLabel } from "@/components/ScopeLabel/ScopeLabel";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Switch } from "@/components/Switch/Switch";
import { clockShort } from "@/lib/clock";
import { mapRows } from "@/lib/setup-map";
import { scopeMeaning, SCOPE_NAMES } from "@/lib/setup-words";
import { decidesHref } from "@/pages/reference/reference-routes";
import { gapOf } from "@/pages/reference/rules-view";
import { t, tn } from "@/strings/t";
import { SetupMapTable } from "./SetupMapTable";
import { SetupBones, SetupError, SetupStale } from "./SetupStates";
import "./YourSetupPage.css";

/** The route param to the Switch's state. Only exactly `scopes=1` is on. */
export function useScopesParam(): [boolean, (on: boolean) => void] {
  const [params, setParams] = useSearchParams();
  const on = params.get("scopes") === "1";
  const set = (next: boolean): void => {
    const copy = new URLSearchParams(params);
    if (next) copy.set("scopes", "1");
    else copy.delete("scopes");
    setParams(copy, { replace: true });
  };
  return [on, set];
}

export function YourSetupPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <YourSetupProject key={project} project={project} />;
}

/** The notice for a project Bar Tab doesn't read: why its project scopes say "Not read here". */
function UnlistedNotice({ project }: { project: string }) {
  return (
    <p className="setup-notice">
      <StatusChip status="unknown">{t("status_unknown")}</StatusChip>
      <HelpButton help="setup.unlisted" />
      <span>{t("su_unlisted", { project })}</span>
      {/* "How a project gets on the list" opens the project picker at the app's root (owner,
          November 10). */}
      <a className="setup-notice-link" href="#/">
        {t("su_unlisted_link")}
      </a>
    </p>
  );
}

interface VersionGapNoticeProps {
  /** The `version_gap` notice's params: installed, checked_on and due, all as text. */
  params: Readonly<Record<string, string>>;
  rules: RulesCard;
}

/**
 * The notice that the Claude Code the owner runs is newer than the version Bar Tab's rules were
 * checked on. It says "its rules" when every rule is due on one version, and how many are due
 * otherwise (the same rule as How Claude Code decides). Its link opens that page with only the due
 * rules. The count comes from the rules when they have loaded, so the link and the page agree, and
 * the notice waits for them, so its words never change after it appears.
 */
function VersionGapNotice({ params, rules }: VersionGapNoticeProps) {
  if (rules.loading) return null;
  const installed = params.installed ?? "";
  const gap = rules.answer === undefined ? null : gapOf(rules.answer);
  const due = gap?.due ?? Number(params.due ?? "0");
  const checkedOn = gap?.checkedOn ?? params.checked_on ?? "";
  return (
    <NoticeLine
      className="setup-version-gap"
      statusWord={t("status_unknown")}
      link={{
        label: tn("dc_gap_link", due),
        href: decidesHref({}, { q: "", confidence: "all", due: true }),
      }}
    >
      {gap?.all === true
        ? t("su_n_version_gap", { installed, checked_on: checkedOn })
        : tn("su_n_version_gap_some", due, { installed, due })}
    </NoticeLine>
  );
}

function YourSetupProject({ project }: { project: string }) {
  const card = useSetupMap(project);
  const rules = useRules();
  const projects = useProjects();
  const [scopesOn, setScopes] = useScopesParam();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const answer = card.answer;
  const title = t("su_card_h");

  let body: React.ReactNode;
  if (answer === undefined) {
    body =
      card.error === null ? (
        <SetupBones line={t("su_ld")} rows={10} />
      ) : (
        <SetupError card={title} onRetry={card.retry} />
      );
  } else {
    body = (
      <>
        {card.failed && <SetupStale receivedAt={card.receivedAt} />}
        <SetupMapTable project={project} rows={mapRows(answer, scopesOn)} scopes={scopesOn} />
        {scopesOn && <ShellLine map={answer} />}
      </>
    );
  }

  return (
    <div className="setup-page">
      <PageHeader
        title={t("su_h1")}
        sub={t("su_sub", { project: projectName })}
        controls={
          <>
            <Switch selected={scopesOn} onChange={setScopes}>
              {t("su_switch")}
            </Switch>
            <HelpButton help="setup.scopes" />
          </>
        }
      />
      {answer?.listed === false && <UnlistedNotice project={projectName} />}
      {answer?.notices.map((notice) =>
        notice.code === "version_gap" ? (
          <VersionGapNotice key={notice.code} params={notice.params} rules={rules} />
        ) : null,
      )}
      <Card
        title={title}
        question={t("su_card_q")}
        right={<HelpButton help="setup.card" />}
        className="setup-map-card"
      >
        {body}
      </Card>
    </div>
  );
}

/** Dates the shell scope: Bar Tab reads the shell's values once, when it starts. */
function ShellLine({ map }: { map: SetupMap }) {
  return (
    <p className="setup-shell-line muted">
      <ScopeLabel
        name={SCOPE_NAMES.shell()}
        meaning={scopeMeaning("shell", clockShort(map.server_started_at))}
      />
    </p>
  );
}
