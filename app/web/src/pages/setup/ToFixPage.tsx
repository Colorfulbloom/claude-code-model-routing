/*
 * The To fix page, #/p/<project>/to-fix. Every problem the setup reads found, in five groups in a
 * fixed order: Couldn't read, Won't load, Not as set, Can't tell and Notices. The first three are
 * counted, and the count is the number in the nav. Each row names the thing, says what is wrong and
 * what it means, and offers one action. M4 has four actions: open the item, copy its path, copy a
 * command Bar Tab never runs, or a line saying why it can't be fixed here. Nothing edits a file.
 *
 * States. First load shows bones with one spoken line. A failed first read shows one raised error
 * with Try again. A refetch that fails keeps the last good rows on screen. With nothing counted the
 * page leads with the empty card, and Can't tell and Notices stay below it. A long group shows its
 * first rows and Show n more. A copy says "Copied" through the page's one polite region.
 */
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router";
import { useProjects } from "@/api/client";
import { useProblems } from "@/api/setup";
import type { ProblemRow } from "@/api/types";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { ToFixGroup } from "@/components/ToFixGroup/ToFixGroup";
import type { ToFixKind } from "@/components/ToFixGroup/ToFixGroup";
import { ToFixRow } from "@/components/ToFixRow/ToFixRow";
import type { ToFixAction } from "@/components/ToFixRow/ToFixRow";
import { clockShort } from "@/lib/clock";
import { fixPlan, problemWords } from "@/lib/problem-words";
import { setupPath } from "@/lib/setup-routes";
import { t, tn } from "@/strings/t";
import "./ToFixPage.css";

/** How many rows a group shows before Show n more, and how many each press adds. */
export const GROUP_PAGE = 25;

type Group = ProblemRow["group"];

interface GroupSpec {
  group: Group;
  kind: ToFixKind;
  title: () => string;
  question: () => string;
}

/** The groups in their fixed order. Each word is a literal t() call. */
const GROUPS: readonly GroupSpec[] = [
  {
    group: "couldnt_read",
    kind: "couldnt_read",
    title: () => t("fx_g_couldnt_read"),
    question: () => t("fx_q_couldnt_read"),
  },
  {
    group: "wont_load",
    kind: "wont_load",
    title: () => t("fx_g_wont_load"),
    question: () => t("fx_q_wont_load"),
  },
  {
    group: "not_as_set",
    kind: "not_as_set",
    title: () => t("fx_g_not_as_set"),
    question: () => t("fx_q_not_as_set"),
  },
  {
    group: "cant_tell",
    kind: "cant_tell",
    title: () => t("fx_g_cant_tell"),
    question: () => t("fx_q_cant_tell"),
  },
  {
    group: "notice",
    kind: "notices",
    title: () => t("fx_g_notice"),
    question: () => t("fx_q_notice"),
  },
];

export function ToFixPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <ToFixProject key={project} project={project} />;
}

/** The action a row offers, worded. */
function actionOf(row: ProblemRow, project: string): ToFixAction {
  const plan = fixPlan(row, project);
  switch (plan.kind) {
    case "open_item":
      return { kind: "open_item", label: plan.label, href: plan.href };
    case "copy_path":
      return {
        kind: "copy_path",
        path: plan.path,
        label: plan.label,
        copiedLabel: t("an_copied"),
        ariaLabel: plan.ariaLabel,
      };
    case "copy_command":
      return {
        kind: "copy_command",
        command: plan.command,
        copyLabel: t("lk_copy"),
        copiedLabel: t("an_copied"),
        ariaLabel: plan.ariaLabel,
        note: plan.note,
      };
    case "cant_fix_here":
      return { kind: "cant_fix_here", reason: plan.reason };
  }
}

function ProblemRowView({ row, project }: { row: ProblemRow; project: string }) {
  const words = problemWords(row);
  // A notice is one counted sentence. It has no title and no action.
  if (row.group === "notice") {
    return <li className="tofix-page-notice">{words.cause}</li>;
  }
  return (
    <ToFixRow
      title={words.title}
      cause={words.cause}
      consequence={words.consequence}
      action={actionOf(row, project)}
      unreadable={row.group === "couldnt_read"}
      onStatus={postStatus}
    />
  );
}

/** One group card with its rows, and Show n more when the group is long. */
function GroupCard({
  spec,
  rows,
  project,
}: {
  spec: GroupSpec;
  rows: readonly ProblemRow[];
  project: string;
}) {
  const [shown, setShown] = useState(GROUP_PAGE);
  const box = useRef<HTMLDivElement>(null);
  const focusAt = useRef<number | null>(null);
  const visible = rows.slice(0, shown);
  const remaining = rows.length - visible.length;
  const title = spec.title();
  const counted = spec.kind !== "cant_tell" && spec.kind !== "notices";

  // After Show n more, focus goes to the first row it added, so a keyboard person keeps their place.
  useEffect(() => {
    const index = focusAt.current;
    if (index === null) return;
    focusAt.current = null;
    const row = box.current?.querySelectorAll("ul.tofix-rows > li")[index];
    row?.querySelector<HTMLElement>("a, button")?.focus();
  }, [shown]);

  return (
    <div className="tofix-page-group" data-group={spec.group} ref={box}>
      <ToFixGroup
        kind={spec.kind}
        title={title}
        count={String(rows.length)}
        {...(counted ? { ariaLabel: t("fx_g_aria", { group: title, n: rows.length }) } : {})}
        note={spec.question()}
      >
        {visible.map((row) => (
          <ProblemRowView key={row.id} row={row} project={project} />
        ))}
        {remaining > 0 && (
          <li className="tofix-page-more">
            <Button
              onPress={() => {
                focusAt.current = visible.length;
                setShown(shown + GROUP_PAGE);
              }}
            >
              {tn("ss_more", Math.min(GROUP_PAGE, remaining))}
            </Button>
          </li>
        )}
      </ToFixGroup>
    </div>
  );
}

function ToFixProject({ project }: { project: string }) {
  const problems = useProblems(project);
  const projects = useProjects();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const answer = problems.answer;

  const counted = answer?.counted ?? 0;
  const sub =
    answer === undefined
      ? undefined
      : counted === 0
        ? t("fx_sub_none", { project: projectName })
        : tn("fx_sub", counted, { project: projectName });

  let body: React.ReactNode;
  if (answer === undefined) {
    body =
      problems.error === null ? (
        <Card title={t("fx_h1")}>
          <SkeletonBones
            label={t("fx_ld", { project: projectName })}
            bones={[{ width: "full" }, { width: "full" }, { width: "l" }]}
          />
        </Card>
      ) : (
        <RaisedFinding
          variant="error"
          title={t("fx_err_h", { project: projectName })}
          actions={<Button onPress={problems.retry}>{t("er_try")}</Button>}
        >
          <p>{t("er_b")}</p>
        </RaisedFinding>
      );
  } else {
    body = (
      <>
        {problems.failed && problems.receivedAt !== null && (
          <p className="tofix-page-stale">
            {t("cd_stale", { time: clockShort(problems.receivedAt) })}
          </p>
        )}
        {counted === 0 && (
          <EmptyState
            variant="page"
            title={t("fx_empty_h")}
            action={{ label: t("fx_empty_a"), href: `#${setupPath(project)}` }}
          >
            {t("fx_empty")}
          </EmptyState>
        )}
        {GROUPS.map((spec) => {
          const rows = answer.rows.filter((row) => row.group === spec.group);
          return rows.length === 0 ? null : (
            <GroupCard key={spec.group} spec={spec} rows={rows} project={project} />
          );
        })}
      </>
    );
  }

  return (
    <div className="tofix-page" aria-busy={answer === undefined && problems.error === null}>
      <PageHeader title={t("fx_h1")} {...(sub !== undefined ? { sub } : {})} />
      {body}
    </div>
  );
}
