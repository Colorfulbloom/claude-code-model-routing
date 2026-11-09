/*
 * The Live page states that have no session on screen (a-m2-p3): nothing running, no sessions at
 * all, session gone, and the lost finding. They share the plain header, an h1 that reads "Live".
 */
import { Link } from "react-aria-components";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { postStatus } from "@/app/harness";
import { CommandRow } from "@/components/CommandRow/CommandRow";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { RunStateGlyph } from "@/components/RunStateGlyph/RunStateGlyph";
import { Well } from "@/components/Well/Well";
import { t } from "@/strings/t";

export interface OtherRunning {
  id: string;
  project: string;
  /** The branch, or the no-branch words. */
  title: string;
  /** "Saltmarsh, 5:48 PM". */
  meta: string;
  state: "working" | "idle";
  stateWord: string;
  href: string;
}

/** A session in another project that is running. Each row opens that project's Live page. */
export function OtherRunningCard({
  items,
  onOpen,
}: {
  items: OtherRunning[];
  onOpen: (item: OtherRunning) => void;
}) {
  if (items.length === 0) return null;
  return (
    <Card title={t("nr_other_h")} question={t("nr_other_q")}>
      <Well variant="list">
        <ul className="live-other">
          {items.map((item) => (
            <li key={item.id}>
              <Link
                className="live-other-link"
                href={item.href}
                onPress={() => {
                  onOpen(item);
                }}
              >
                <span className="live-other-name">{item.title}</span>
                <span className="live-other-meta muted">{item.meta}</span>
                <RunStateGlyph state={item.state} className="live-other-state">
                  {item.stateWord}
                </RunStateGlyph>
                <span className="live-other-chev" aria-hidden="true">
                  {"›"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Well>
    </Card>
  );
}

function EmptyCard({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="card live-empty" aria-labelledby="live-empty-h">
      <span className="live-empty-mark" aria-hidden="true">
        {"◌"}
      </span>
      <h2 className="live-empty-title" id="live-empty-h">
        {title}
      </h2>
      <p className="muted live-empty-body">{body}</p>
      {children}
    </section>
  );
}

/** Nothing is running in this project, and there is an ended session to open. */
export function NothingRunning({
  project,
  last,
}: {
  project: string;
  last: { meta: string; onOpen: () => void } | null;
}) {
  return (
    <EmptyCard title={t("nr_h", { project })} body={t("nr_b")}>
      {last !== null && (
        <div className="live-acts">
          <Button variant="primary" onPress={last.onOpen}>
            {t("nr_last")}
          </Button>
          <span className="muted">{last.meta}</span>
        </div>
      )}
    </EmptyCard>
  );
}

/** The project has no session at all. The command starts one. */
export function NoSessions({ project, path }: { project: string; path: string }) {
  return (
    <EmptyCard title={t("ns_h", { project })} body={t("ns_b")}>
      <CommandRow
        className="live-cmd"
        command={`cd ${path} && claude`}
        copyLabel={t("lk_copy")}
        copiedLabel={t("cs_copied")}
        onStatus={postStatus}
      />
    </EmptyCard>
  );
}

/** The link names a session this project does not have. */
export function SessionGone({
  project,
  running,
  allHref,
}: {
  project: string;
  running: { meta: string; onOpen: () => void } | null;
  allHref: string;
}) {
  return (
    <RaisedFinding variant="error" title={t("gone_h", { project })} className="live-gone">
      <p>{t("gone_b")}</p>
      {running !== null && (
        <div className="live-acts">
          <Button variant="primary" onPress={running.onOpen}>
            {t("gone_open")}
          </Button>
          <span className="muted">{running.meta}</span>
        </div>
      )}
      <p>
        <Link className="live-link" href={allHref}>
          {t("gone_all")}
        </Link>
      </p>
    </RaisedFinding>
  );
}

/** Three polls in a row failed. The last good numbers stay on screen below it. */
export function LostFinding({
  time,
  onRetry,
}: {
  /** When the last good answer came, or null when there never was one. */
  time: string | null;
  onRetry: () => void;
}) {
  return (
    <RaisedFinding
      variant="warning"
      title={t("lost_h")}
      className="live-lost"
      actions={<Button onPress={onRetry}>{t("lost_try")}</Button>}
    >
      {time !== null && <p>{t("lost_b", { time })}</p>}
    </RaisedFinding>
  );
}
