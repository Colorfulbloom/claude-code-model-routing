/* Model check: findings for the agents that did not run as their file sets, then one line for the rest. */
import { Card } from "@/components/Card/Card";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import type { SettingStatus } from "@/components/StatusChip/StatusChip";
import type { McView } from "@/lib/model-check";
import { STATUS_WORDS } from "@/lib/model-check";
import { t } from "@/strings/t";

/** Lowered keeps the check edge. Anything that went against the setup takes the warning edge. */
function variantFor(status: SettingStatus | null): "plain" | "check" | "warning" {
  if (status === "lowered") return "check";
  if (status === null || status === "default") return "plain";
  return "warning";
}

export function ModelCheckCard({ view }: { view: McView }) {
  return (
    <Card title={t("mc_h")} question={t("mc_q")}>
      <div className="live-mc">
        {view.findings.map((finding) => (
          <RaisedFinding key={finding.id} variant={variantFor(finding.status)}>
            <h3 className="live-mc-title">
              {finding.status !== null && (
                <StatusChip status={finding.status}>{STATUS_WORDS[finding.status]}</StatusChip>
              )}
              <span>{finding.title}</span>
            </h3>
            <p className="live-mc-body muted">{finding.body}</p>
          </RaisedFinding>
        ))}
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

export function ModelCheckLoading() {
  return (
    <Card title={t("mc_h")} question={t("mc_q")}>
      <SkeletonBones label="" bones={[{ width: "full" }, { width: "l" }, { width: "m" }]} />
    </Card>
  );
}
