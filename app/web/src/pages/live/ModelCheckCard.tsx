/*
 * Model check: findings for the agents that did not run as their file sets, then one line for the
 * rest. Live shows each finding as a raised card with a title and its reason. Review passes
 * `compact` and gets the board's one-line rows, a chip and one sentence per finding.
 */
import { Card } from "@/components/Card/Card";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import type { SettingStatus } from "@/components/StatusChip/StatusChip";
import type { McView } from "@/lib/model-check";
import { STATUS_WORDS } from "@/lib/model-check";
import { t } from "@/strings/t";
import "./ModelCheckCard.css";

/** Lowered keeps the check edge. Anything that went against the setup takes the warning edge. */
function variantFor(status: SettingStatus | null): "plain" | "check" | "warning" {
  if (status === "lowered") return "check";
  if (status === null || status === "default") return "plain";
  return "warning";
}

/** `question` replaces the card's question line. Summary puts its count of agents there. */
export function ModelCheckCard({
  view,
  question,
  note,
  compact = false,
}: {
  view: McView;
  question?: string;
  /** A line above the findings, such as the stale-refresh line. */
  note?: React.ReactNode;
  /** One grey row per finding, a chip and one sentence, with no reason and no edge. */
  compact?: boolean;
}) {
  return (
    <Card title={t("mc_h")} question={question ?? t("mc_q")}>
      <div className="live-mc">
        {note}
        {compact ? (
          <ul className="live-mc-rows">
            {view.findings.map((finding) => (
              <li key={finding.id} className="live-mc-row" data-chip={finding.status !== null}>
                {finding.status !== null && (
                  <StatusChip status={finding.status}>{STATUS_WORDS[finding.status]}</StatusChip>
                )}
                <span>{finding.oneLine ?? finding.title}</span>
              </li>
            ))}
          </ul>
        ) : (
          view.findings.map((finding) => (
            <RaisedFinding key={finding.id} variant={variantFor(finding.status)}>
              <h3 className="live-mc-title">
                {finding.status !== null && (
                  <StatusChip status={finding.status}>{STATUS_WORDS[finding.status]}</StatusChip>
                )}
                <span>{finding.title}</span>
              </h3>
              <p className="live-mc-body muted">{finding.body}</p>
            </RaisedFinding>
          ))
        )}
        {view.noFileLine !== null && <p className="live-mc-line muted">{view.noFileLine}</p>}
        {view.okLine !== null && (
          <p className="live-mc-ok">
            <StatusChip status="in_effect">{STATUS_WORDS.in_effect}</StatusChip>
            <span>{view.okLine}</span>
          </p>
        )}
      </div>
    </Card>
  );
}

/** `label` is the one line a screen reader hears. Live passes none, Summary says what loads. */
export function ModelCheckLoading({ label = "" }: { label?: string }) {
  return (
    <Card title={t("mc_h")} question={t("mc_q")}>
      <SkeletonBones label={label} bones={[{ width: "full" }, { width: "l" }, { width: "m" }]} />
    </Card>
  );
}
