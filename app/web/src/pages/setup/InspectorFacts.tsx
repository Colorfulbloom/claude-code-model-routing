/*
 * The inspector's facts for one kind of item: the lines that differ by part. An agent shows its
 * front matter fields (and the ones Claude Code ignores in a plugin's agents), an instruction file
 * its import chain, a rules file the globs it loads for, a skill how to call it, a hook its event
 * and command, a permission its tool and pattern, an MCP server how it connects, a plugin its
 * version and what it adds, and an output style whether it is built in. Every value that can hold a
 * secret comes as MaskedText and shows the masked mark.
 */
import { Link } from "react-aria-components";
import type { SetupItem } from "@/api/types";
import { ValueText } from "@/components/ListInspector/ValueText";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Well } from "@/components/Well/Well";
import { modelFamily, modelLabel } from "@/lib/models";
import { itemName } from "@/lib/setup-list";
import { isSetupPart, setupItemPathFromId } from "@/lib/setup-routes";
import { PART_NAMES, codeWord, scopeName, statusWord } from "@/lib/setup-words";
import { t, tn } from "@/strings/t";

const AGENT_FIELD_LABELS: Readonly<Record<string, () => string>> = {
  description: () => t("ag_f_desc"),
  tools: () => t("ag_f_tools"),
  color: () => t("ag_f_color"),
  model: () => t("ag_f_model"),
  effort: () => t("ag_f_effort"),
  permissionMode: () => t("ag_f_perm"),
  hooks: () => t("ag_f_hooks"),
  mcpServers: () => t("ag_f_mcp"),
};

function agentFieldLabel(name: string): string {
  const known = Object.hasOwn(AGENT_FIELD_LABELS, name) ? AGENT_FIELD_LABELS[name] : undefined;
  return known === undefined ? name : known();
}

/** Label and value pairs in a definition list. */
function Dl({ rows }: { rows: { key: string; label: string; value: React.ReactNode }[] }) {
  return (
    <dl className="setup-facts">
      {rows.map((row) => (
        <div key={row.key} className="setup-fact">
          <dt className="setup-fact-label">{row.label}</dt>
          <dd className="setup-fact-value">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="setup-facts-section">
      <h3 className="setup-h3">{title}</h3>
      {children}
    </div>
  );
}

const masked = (text: string, isMasked: boolean) => ({ text, masked: isMasked });

function Val({ text, isMasked }: { text: string; isMasked: boolean }) {
  return <ValueText value={masked(text, isMasked)} maskedLabel={t("in_masked_word")} />;
}

function Code({ text, isMasked = false }: { text: string; isMasked?: boolean }) {
  return (
    <code className="setup-code">
      <Val text={text} isMasked={isMasked} />
    </code>
  );
}

/** A hook's matcher in code. It breaks after a bar and never inside a tool name. */
function MatcherCode({ text }: { text: string }) {
  const names = text.split("|");
  return (
    <code className="setup-code setup-matcher">
      {names.map((name, index) => (
        <span key={`${name}:${String(index)}`}>
          {index > 0 && (
            <>
              {"|"}
              <wbr />
            </>
          )}
          {name}
        </span>
      ))}
    </code>
  );
}

function LineMark({ line }: { line: number | null }) {
  return line === null ? null : (
    <small className="setup-line muted">{t("in_line", { n: line })}</small>
  );
}

function AgentFacts({ item }: { item: SetupItem }) {
  const facts = item.facts.agent;
  if (facts === null || facts === undefined) return null;
  const shown = facts.fields.filter((f) => !f.ignored && f.name !== "name");
  const ignored = facts.fields.filter((f) => f.ignored);
  return (
    <>
      {ignored.length > 0 && (
        <Section title={t("ag_ignored_h")}>
          <p className="setup-small muted">{t("ag_ignored_b")}</p>
          <Well variant="list">
            <ul className="setup-ignored">
              {ignored.map((f) => (
                <li key={f.name} className="setup-ignored-row">
                  <code className="setup-code">{f.name}</code>
                  {f.value !== null && (
                    <b className="setup-ignored-value">
                      <Val text={f.value.text} isMasked={f.value.masked} />
                    </b>
                  )}
                  <StatusChip status="ignored">{statusWord("ignored")}</StatusChip>
                  <LineMark line={f.line} />
                </li>
              ))}
            </ul>
          </Well>
        </Section>
      )}
      {shown.length > 0 && (
        <Section title={t("in_details_h")}>
          <Dl
            rows={shown.map((f) => {
              const text = f.value?.text ?? "";
              const family = f.name === "model" ? modelFamily(text) : null;
              return {
                key: f.name,
                label: agentFieldLabel(f.name),
                value: (
                  <>
                    {family !== null && <ModelSwatch model={family} />}
                    {f.name === "model" ? (
                      <span>{modelLabel(text)}</span>
                    ) : f.name === "tools" ? (
                      <Code text={text} isMasked={f.value?.masked ?? false} />
                    ) : (
                      <Val text={text} isMasked={f.value?.masked ?? false} />
                    )}
                    <LineMark line={f.line} />
                  </>
                ),
              };
            })}
          />
        </Section>
      )}
    </>
  );
}

function ImportState({ state }: { state: "read" | "missing" | "cycle" | "too_deep" | "not_read" }) {
  const text = codeWord("ins_imp_", state);
  if (state === "read") return <span className="muted">{text}</span>;
  return (
    <>
      <StatusChip status={state === "not_read" ? "unknown" : "invalid"}>
        {statusWord(state === "not_read" ? "unknown" : "invalid")}
      </StatusChip>
      <span className="muted setup-small">{text}</span>
    </>
  );
}

function InstructionFacts({ item, project, scopes }: Props) {
  const facts = item.facts.instruction;
  if (facts === null || facts === undefined) return null;
  return (
    <Section title={t("ins_imports_h")}>
      <Well variant="list">
        <ol className="setup-chain">
          <li className="setup-chain-row" style={{ "--d": 0 } as React.CSSProperties}>
            <code className="setup-code">{itemName(item)}</code>
            <span className="muted">{tn("ins_lines", facts.lines)}</span>
          </li>
          {facts.imports.map((imp, index) => {
            const path =
              imp.target_item === null
                ? null
                : setupItemPathFromId(project, imp.target_item, scopes);
            return (
              <li
                key={`${imp.target}:${String(index)}`}
                className="setup-chain-row"
                style={{ "--d": Math.max(imp.depth, 1) } as React.CSSProperties}
              >
                {path === null ? (
                  <code className="setup-code">{`@${imp.target}`}</code>
                ) : (
                  <Link className="setup-chain-link" href={`#${path}`}>
                    <code className="setup-code">{`@${imp.target}`}</code>
                  </Link>
                )}
                <span className="setup-chain-state">
                  <ImportState state={imp.state} />
                </span>
              </li>
            );
          })}
        </ol>
      </Well>
    </Section>
  );
}

function RulesFacts({ item }: { item: SetupItem }) {
  const globs = item.loads?.kind === "on_demand" ? item.loads.globs : [];
  if (globs.length === 0) return null;
  return (
    <Section title={t("ru_globs_h")}>
      <Well variant="list">
        <ul className="setup-globs">
          {globs.map((g) => (
            <li key={g}>
              <code className="setup-code">{g}</code>
            </li>
          ))}
        </ul>
      </Well>
    </Section>
  );
}

function SkillFacts({ item }: { item: SetupItem }) {
  const facts = item.facts.skill;
  if (facts === null || facts === undefined) return null;
  const rows = [
    ...(facts.description !== null
      ? [
          {
            key: "desc",
            label: t("ag_f_desc"),
            value: <Val text={facts.description.text} isMasked={facts.description.masked} />,
          },
        ]
      : []),
    { key: "call", label: t("sk_call"), value: <Code text={facts.invoke} /> },
  ];
  return (
    <Section title={t("in_details_h")}>
      <Dl rows={rows} />
      {facts.legacy_command && <p className="setup-small muted">{t("sk_legacy")}</p>}
    </Section>
  );
}

function HookFacts({ item }: { item: SetupItem }) {
  const facts = item.facts.hook;
  if (facts === null || facts === undefined) return null;
  const rows = [
    {
      key: "event",
      label: t("hk_f_event"),
      value: (
        <>
          <span>{codeWord("hk_ev_", facts.event)}</span> <Code text={facts.event} />
        </>
      ),
    },
    {
      key: "matcher",
      label: t("hk_f_matcher"),
      value:
        facts.matcher === null || facts.matcher === "" ? (
          <span>{t("hk_no_matcher")}</span>
        ) : (
          <MatcherCode text={facts.matcher} />
        ),
    },
    {
      key: "type",
      label: t("hk_f_type"),
      value: <span>{codeWord("hk_ty_", facts.handler_type)}</span>,
    },
    ...(facts.command !== null
      ? [
          {
            key: "cmd",
            label: t("hk_f_cmd"),
            value: <Code text={facts.command.text} isMasked={facts.command.masked} />,
          },
        ]
      : []),
    ...(facts.timeout !== null
      ? [
          {
            key: "timeout",
            label: t("hk_f_timeout"),
            value: <span>{t("hk_timeout_v", { n: facts.timeout })}</span>,
          },
        ]
      : []),
  ];
  return (
    <Section title={t("in_details_h")}>
      <Dl rows={rows} />
    </Section>
  );
}

function PermissionFacts({ item }: { item: SetupItem }) {
  const facts = item.facts.permission;
  if (facts === null || facts === undefined) return null;
  if (facts.kind === "default_mode") {
    const mode = item.effective?.value?.text;
    return mode === undefined ? null : (
      <Section title={t("in_details_h")}>
        <Dl rows={[{ key: "mode", label: t("pm_f_mode"), value: <span>{mode}</span> }]} />
      </Section>
    );
  }
  if (facts.kind === "directory") {
    return (
      <Section title={t("in_details_h")}>
        <Dl rows={[{ key: "folder", label: t("pm_f_folder"), value: <Code text={item.name} /> }]} />
      </Section>
    );
  }
  const tool = facts.tool ?? item.name;
  return (
    <Section title={t("in_details_h")}>
      <Dl
        rows={[
          { key: "tool", label: t("pm_f_tool"), value: <span>{tool}</span> },
          {
            key: "match",
            label: t("pm_f_match"),
            value:
              facts.pattern === null ? (
                <span>{t("pm_match_any", { tool })}</span>
              ) : (
                <Code text={facts.pattern} />
              ),
          },
        ]}
      />
    </Section>
  );
}

function McpFacts({ item }: { item: SetupItem }) {
  const facts = item.facts.mcp;
  if (facts === null || facts === undefined) return null;
  const envNames = Object.keys(facts.env);
  const headers = Object.entries(facts.headers);
  const rows = [
    {
      key: "transport",
      label: t("mc_f_transport"),
      value: <span>{codeWord("mc_t_", facts.transport)}</span>,
    },
    ...(facts.command !== null
      ? [
          {
            key: "cmd",
            label: t("mc_f_cmd"),
            value: <Code text={facts.command.text} isMasked={facts.command.masked} />,
          },
        ]
      : []),
    ...(facts.url !== null
      ? [
          {
            key: "url",
            label: t("mc_f_url"),
            value: <Code text={facts.url.text} isMasked={facts.url.masked} />,
          },
        ]
      : []),
    ...(facts.args.length > 0
      ? [
          {
            key: "args",
            label: t("mc_f_args"),
            value: (
              <span className="setup-names">
                {facts.args.map((a, i) => (
                  <Code key={`${a.text}:${String(i)}`} text={a.text} isMasked={a.masked} />
                ))}
              </span>
            ),
          },
        ]
      : []),
    ...(envNames.length > 0
      ? [
          {
            key: "env",
            label: t("mc_f_env"),
            value: (
              <>
                <span className="setup-names">
                  {envNames.map((name) => (
                    <Code key={name} text={name} />
                  ))}
                </span>
                <small className="muted">{tn("mc_f_env_v", envNames.length)}</small>
              </>
            ),
          },
        ]
      : []),
    ...(headers.length > 0
      ? [
          {
            key: "headers",
            label: t("mc_f_headers"),
            value: (
              <span className="setup-names">
                {headers.map(([name, value]) => (
                  <span key={name}>
                    <code className="setup-code">{name}</code>{" "}
                    <Val text={value.text} isMasked={value.masked} />
                  </span>
                ))}
              </span>
            ),
          },
        ]
      : []),
    ...(facts.approved !== null
      ? [
          {
            key: "approved",
            label: t("mc_f_approved"),
            value: <span>{facts.approved ? t("mc_yes") : t("mc_no")}</span>,
          },
        ]
      : []),
  ];
  return (
    <Section title={t("in_details_h")}>
      <Dl rows={rows} />
    </Section>
  );
}

function PluginFacts({ item, project, scopes }: Props) {
  const facts = item.facts.plugin;
  if (facts === null || facts === undefined) return null;
  const rows = [
    ...(facts.version !== null
      ? [{ key: "version", label: t("pl_f_version"), value: <span>{facts.version}</span> }]
      : []),
    ...(facts.marketplace !== null
      ? [{ key: "market", label: t("pl_f_marketplace"), value: <span>{facts.marketplace}</span> }]
      : []),
    ...(facts.enabled.length > 0
      ? [
          {
            key: "enabled",
            label: t("pl_f_enabled"),
            value: (
              <span className="setup-names">
                {facts.enabled.map((s) => (
                  <span key={s.scope}>
                    {scopeName(s.scope)} {s.enabled ? t("pl_on") : t("pl_off")}
                  </span>
                ))}
              </span>
            ),
          },
        ]
      : []),
    ...(facts.orphaned_versions.length > 0
      ? [
          {
            key: "orphaned",
            label: t("pl_f_orphaned"),
            value: (
              <span className="setup-names">
                {facts.orphaned_versions.map((v) => (
                  <Code key={v} text={v} />
                ))}
              </span>
            ),
          },
        ]
      : []),
  ];
  return (
    <>
      {rows.length > 0 && (
        <Section title={t("in_details_h")}>
          <Dl rows={rows} />
        </Section>
      )}
      {facts.contents.length > 0 && (
        <Section title={t("pl_contents_h")}>
          <Well variant="list">
            <ul className="setup-contents">
              {facts.contents.map((id) => {
                const colon = id.indexOf(":");
                const part = id.slice(0, Math.max(colon, 0));
                const path = setupItemPathFromId(project, id, scopes);
                return (
                  <li key={id} className="setup-contents-row">
                    <span className="muted">{isSetupPart(part) ? PART_NAMES[part]() : part}</span>
                    {path === null ? (
                      <span>{id.slice(colon + 1)}</span>
                    ) : (
                      <Link className="setup-chain-link" href={`#${path}`}>
                        {id.slice(colon + 1)}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </Well>
        </Section>
      )}
    </>
  );
}

function OutputStyleFacts({ item }: { item: SetupItem }) {
  const facts = item.facts.output_style;
  if (facts === null || facts === undefined) return null;
  if (facts.active === null) return null;
  return (
    <Section title={t("in_details_h")}>
      <Dl
        rows={[
          {
            key: "active",
            label: t("sf_output_style"),
            value: (
              <>
                <span>{facts.active}</span>
                {facts.builtin && <small className="muted">{t("st_builtin")}</small>}
              </>
            ),
          },
        ]}
      />
    </Section>
  );
}

interface Props {
  item: SetupItem;
  project: string;
  scopes: boolean;
}

/** The facts section for the item's part. Settings have none, because their where-set rows say it all. */
export function InspectorFacts({ item, project, scopes }: Props) {
  switch (item.part) {
    case "agents":
      return <AgentFacts item={item} />;
    case "instructions":
      return <InstructionFacts item={item} project={project} scopes={scopes} />;
    case "rules":
      return <RulesFacts item={item} />;
    case "skills":
      return <SkillFacts item={item} />;
    case "hooks":
      return <HookFacts item={item} />;
    case "permissions":
      return <PermissionFacts item={item} />;
    case "mcp":
      return <McpFacts item={item} />;
    case "plugins":
      return <PluginFacts item={item} project={project} scopes={scopes} />;
    case "output_style":
      return <OutputStyleFacts item={item} />;
    case "settings":
      return null;
  }
}
