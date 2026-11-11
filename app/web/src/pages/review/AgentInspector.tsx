/*
 * The inspector beside the Agents table, for one agent. Every setup line comes from the
 * `agents:<...>` item of /api/setup/agents, the same item `setup/agents/<name>` reads. Cost, runs
 * and Ran with come from /api/agents over the page's range. A plugin or managed agent shows its
 * owner and a Copy path inside the read-only box, and no editor. A plugin's ignored fields keep
 * their value and line. An item that is no longer in the part shows one sentence and a link back
 * to the list, and the link takes focus (need 27).
 */
import { useEffect, useRef } from "react";
import { Link } from "react-aria-components";
import { useSetupPart } from "@/api/setup";
import type { AgentList, ReviewRange, SetupItem } from "@/api/types";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { CopyPath } from "@/components/CopyPath/CopyPath";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { Inspector } from "@/components/ListInspector/Inspector";
import type { InspectorReadOnly } from "@/components/ListInspector/Inspector";
import { ValueText } from "@/components/ListInspector/ValueText";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { postStatus } from "@/app/harness";
import { agentCheckView } from "@/lib/agent-check";
import { agentUsageLine } from "@/lib/agent-usage";
import { modelFamily, modelLabel } from "@/lib/models";
import { STATUS_WORDS } from "@/lib/model-check";
import { word } from "@/lib/problem-words";
import { reviewPath } from "@/lib/range";
import { originNote } from "@/lib/setup-inspector";
import { setupItemPathFromId } from "@/lib/setup-routes";
import { AgentCallout } from "@/pages/setup/AgentCallout";
import { t } from "@/strings/t";
import { CardBones, CardError } from "./CardStates";

type SetupSource = SetupItem["sources"][number];

export interface AgentInspectorProps {
  project: string;
  range: ReviewRange;
  /** The item key in the URL, `judge` or `lint-kit:linter`. */
  itemKey: string;
  /** The page's agents answer, for cost, runs and sessions. Undefined while it loads. */
  agents: AgentList | undefined;
  /** Phone only. Shows the back link and takes the page. */
  back?: { href: string };
  /** True when a person opened this agent from the table, so the h2 takes focus. */
  focus: boolean;
}

/** "line 3" in a location, "agents/linter.md line 3", or the file alone. Empty without a file. */
function whereOf(source: SetupSource | undefined): string {
  if (source === undefined || source.file === null) return "";
  return source.line === null
    ? t("loc_file", { file: source.file })
    : t("loc_line", { file: source.file, line: source.line });
}

/** The model and effort that run, read from the item's effective value, "model / effort". */
function effectivePair(item: SetupItem): { model?: string; effort?: string } {
  const text = item.effective?.value?.text ?? "";
  const parts = text === "" ? [] : text.split(" / ");
  if (parts.length >= 2) return { model: parts[0] ?? "", effort: parts[1] ?? "" };
  const only = parts[0];
  if (only === undefined) return {};
  // One value is a model when it names one, and an effort when it does not.
  return modelFamily(only) !== null ? { model: only } : { effort: only };
}

/**
 * The "Runs on X at Y" line, and the note that names why it differs from the file. The note comes
 * from the pill's status and the check's code (`originNote`), never from the effective value, so
 * an Overridden pill is never next to a cap sentence. Null when nothing says what runs.
 */
function runsLine(item: SetupItem): { text: string; note: string | null } | null {
  const origin = originNote(item);
  if (origin?.kind === "unknown") return { text: origin.text, note: null };
  const { model, effort } = effectivePair(item);
  let text: string | null = null;
  if (model !== undefined && effort !== undefined) {
    text = t("ag_runs", { model: modelLabel(model), effort });
  } else if (model !== undefined) {
    text = t("in_runs_model", { value: modelLabel(model) });
  } else if (effort !== undefined) {
    text = t("in_runs_effort", { value: effort });
  } else if (item.effective?.origin === "default") {
    text = t("in_origin_default");
  }
  if (text === null) return null;
  return { text, note: origin === null ? null : origin.text };
}

/** The "Set in User, file line 4" line. */
function setLine(item: SetupItem, nameSource: SetupSource | undefined): string | null {
  const where = whereOf(nameSource);
  if (where === "") return null;
  const plugin = item.facts.agent?.plugin ?? null;
  if (item.scope === "plugin" && plugin !== null) return t("in_set_plugin", { plugin, where });
  const scope = word(item.scope === null ? "sc_none" : `sc_${item.scope}`) ?? "";
  return t("in_set_at", { scope, where });
}

/** The Why line. A reason with a variant for a missing other file reads the shorter one. */
function whyLine(item: SetupItem): string | null {
  const reason = item.reason;
  if (reason === null) return null;
  const needsOther = reason.code === "agent_overrides" || reason.code === "same_name_in_folder";
  const key =
    needsOther && reason.params.other_file === undefined
      ? `rs_${reason.code}_noother`
      : `rs_${reason.code}`;
  return word(key, reason.params);
}

/** How sure the page is, in words. */
function confidenceLine(item: SetupItem): string {
  const { level, tested_on: version } = item.confidence;
  if (level === "tested") {
    return version === null ? t("in_conf_tested_nover") : t("in_conf_tested", { version });
  }
  return level === "documented" ? t("in_conf_documented") : t("in_conf_assumed");
}

/** The label of a front matter field. A field the deck has no word for shows as written. */
function fieldLabel(name: string): string {
  switch (name) {
    case "description":
      return t("ag_f_desc");
    case "tools":
      return t("ag_f_tools");
    case "color":
      return t("ag_f_color");
    case "model":
      return t("ag_f_model");
    case "effort":
      return t("ag_f_effort");
    case "permissionMode":
      return t("ag_f_perm");
    case "hooks":
      return t("ag_f_hooks");
    case "mcpServers":
      return t("ag_f_mcp");
    default:
      return name;
  }
}

function Details({ item }: { item: SetupItem }) {
  const fields = (item.facts.agent?.fields ?? []).filter((f) => !f.ignored && f.name !== "name");
  if (fields.length === 0) return null;
  return (
    <div>
      <h3 className="inspector-h3">
        <HelpTerm help="agents.inspector">{t("in_details_h")}</HelpTerm>
      </h3>
      <dl className="review-agents-details">
        {fields.map((field) => {
          const text = field.value?.text ?? "";
          const family = field.name === "model" ? modelFamily(text) : null;
          return (
            <div key={field.name} className="review-agents-detail">
              <dt>{fieldLabel(field.name)}</dt>
              <dd>
                {family !== null && <ModelSwatch model={family} />}
                {field.value === null ? (
                  ""
                ) : field.name === "model" ? (
                  <ValueText
                    value={{ text: modelLabel(text), masked: field.value.masked }}
                    maskedLabel={t("in_masked_aria")}
                  />
                ) : (
                  <ValueText value={field.value} maskedLabel={t("in_masked_aria")} />
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

function Ignored({ item }: { item: SetupItem }) {
  const fields = (item.facts.agent?.fields ?? []).filter((f) => f.ignored);
  if (fields.length === 0) return null;
  const file = item.sources.find((s) => s.key === "name")?.file ?? "";
  return (
    <div>
      <h3 className="inspector-h3">
        <HelpTerm help="agents.inspector">{t("ag_ignored_h")}</HelpTerm>
      </h3>
      <p className="muted review-agents-ignored-note">{t("ag_ignored_b")}</p>
      <ul className="review-agents-ignored">
        {fields.map((field) => (
          <li key={field.name}>
            <span>
              <code>{field.name}</code>{" "}
              {field.value !== null && (
                <b>
                  <ValueText value={field.value} maskedLabel={t("in_masked_aria")} />
                </b>
              )}
            </span>
            <StatusChip status="ignored">{STATUS_WORDS.ignored}</StatusChip>
            {file !== "" && (
              <code>{field.line === null ? file : `${file}:${String(field.line)}`}</code>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ItemInspector({
  project,
  item,
  agents,
  range,
  back,
  focus,
}: {
  project: string;
  item: SetupItem;
  agents: AgentList | undefined;
  range: ReviewRange;
  back: AgentInspectorProps["back"];
  focus: boolean;
}) {
  const nameSource = item.sources.find((s) => s.key === "name");
  const fullPath = nameSource?.full_path ?? null;
  const only = item.read_only_reason;
  const owner = item.facts.agent?.plugin ?? only?.params.plugin ?? "";

  let readOnly: InspectorReadOnly | undefined;
  if (only?.code === "managed") {
    readOnly = { lockLabel: t("ro_h"), reason: t("ro_managed") };
  } else if (only?.code === "plugin") {
    readOnly = {
      lockLabel: t("ro_h"),
      reason: `${t("ro_plugin", { plugin: owner })} ${t("ro_plugin_2")}`,
    };
  } else if (only === null) {
    // M6a has no agent editing. The box says it comes next and keeps Copy path.
    readOnly = { lockLabel: t("ro_h"), reason: t("ro_agents_next") };
  }
  const copy =
    fullPath === null
      ? null
      : {
          value: fullPath,
          label: t("in_copy"),
          copiedLabel: t("an_copied"),
        };
  if (readOnly !== undefined && copy !== null) readOnly = { ...readOnly, path: copy };

  const setupPath = setupItemPathFromId(project, item.id);
  const runs = runsLine(item);
  const setTo = setLine(item, nameSource);
  const why = whyLine(item);
  const usage = agentUsageLine(item, agents, range);
  const check = agentCheckView(item);

  return (
    <Inspector
      title={item.name}
      status={{ status: item.status, label: STATUS_WORDS[item.status] }}
      focusOnMount={focus}
      className="review-agents-inspector"
      {...(back !== undefined
        ? { back: { label: t("sp_back", { part: t("sf_agents") }), href: back.href } }
        : {})}
      {...(runs !== null
        ? {
            runs: (
              <>
                {runs.text}
                {runs.note !== null && (
                  <span className="muted review-agents-cap"> {runs.note}</span>
                )}
              </>
            ),
          }
        : {})}
      {...(setTo !== null ? { setTo } : {})}
      {...(readOnly !== undefined ? { readOnly } : {})}
      {...(check !== null ? { check: <AgentCallout view={check} /> } : {})}
      {...(why !== null
        ? { why: { title: t("in_why_h"), body: why, confidence: confidenceLine(item) } }
        : {})}
      {...(usage !== null ? { usage } : {})}
      actions={
        <>
          {readOnly === undefined && copy !== null && (
            <CopyPath
              value={copy.value}
              label={copy.label}
              copiedLabel={copy.copiedLabel}
              onStatus={postStatus}
            />
          )}
          {setupPath !== null && (
            <Button variant="quiet" href={`#${setupPath}`}>
              {t("ag_open_setup")} <span aria-hidden="true">→</span>
            </Button>
          )}
        </>
      }
    >
      {item.real_path !== null && <p className="muted">{t("in_link", { path: item.real_path })}</p>}
      <Ignored item={item} />
      <Details item={item} />
    </Inspector>
  );
}

/** The sentence for an item that is no longer in the part, with a link back that takes focus. */
function Vanished({ href }: { href: string }) {
  const link = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    link.current?.focus();
  }, []);
  return (
    <Card title={t("sp_gone_h", { part: t("sf_agents") })}>
      <p className="muted">{t("sp_gone_b")}</p>
      <Link className="review-agents-open" href={href} ref={link}>
        {t("sp_back", { part: t("sf_agents") })}
      </Link>
    </Card>
  );
}

export function AgentInspector({
  project,
  range,
  itemKey,
  agents,
  back,
  focus,
}: AgentInspectorProps) {
  const part = useSetupPart(project, "agents");
  const listHref = `#${reviewPath(project, "agents", range)}`;
  const id = `agents:${itemKey}`;
  const answer = part.answer;

  if (answer === undefined) {
    return (
      <Card title={t("sf_agents")}>
        {part.error === null ? (
          <CardBones card={t("sf_agents")} rows={5} />
        ) : (
          <CardError card={t("sf_agents")} onRetry={part.retry} />
        )}
      </Card>
    );
  }
  const item = answer.items.find((i) => i.id === id);
  if (item === undefined) return <Vanished href={listHref} />;
  return (
    <ItemInspector
      key={id}
      project={project}
      item={item}
      agents={agents}
      range={range}
      back={back}
      focus={focus}
    />
  );
}
