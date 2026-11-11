/*
 * The three Summary cards under the chart, all from the one summary answer: where the money went,
 * the model check over the range, and the most expensive sessions. Each shows its own bones, its
 * own error and the stale line, so one failing part never blanks the page.
 */
import type { ReviewRange, Summary } from "@/api/types";
import type { SummaryCard } from "@/api/review";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { ShareBar } from "@/components/ShareBar/ShareBar";
import { Well } from "@/components/Well/Well";
import { reviewPath } from "@/lib/range";
import { buildMoney, buildTopSessions } from "@/lib/review-cards";
import { buildModelCheck, checkCounts } from "@/lib/model-check";
import { t, tn } from "@/strings/t";
import "../LivePage.css";
import { ModelCheckCard, ModelCheckLoading } from "../live/ModelCheckCard";
import { CardBones, CardError, StaleLine } from "./CardStates";
import { SessionsTable } from "./SessionsTable";
import "./SummaryCards.css";

export function MoneyCard({ card }: { card: SummaryCard }) {
  const answer = card.answer;
  const title = t("rv_who_h");
  let body: React.ReactNode;
  if (answer === undefined) {
    body =
      card.error === null ? (
        <CardBones card={title} rows={4} />
      ) : (
        <CardError card={title} onRetry={card.retry} />
      );
  } else {
    body = (
      <Well variant="list">
        <ul className="review-money">
          {buildMoney(answer).map((row) => (
            <ShareBar
              key={row.id}
              model={row.model}
              name={
                <span className="review-agent-name">
                  <span className="review-agent-title">{row.name}</span>
                  {row.modelName !== null && <small className="muted">{row.modelName}</small>}
                </span>
              }
              share={row.fill}
              value={row.value}
              {...(row.percent !== undefined ? { percent: row.percent } : {})}
            />
          ))}
        </ul>
      </Well>
    );
  }
  return (
    <Card title={title} question={t("rv_who_q")} right={<HelpButton help="summary.who" />}>
      {card.failed && <StaleLine updatedAt={card.updatedAt} />}
      {body}
    </Card>
  );
}

/** The model check count for the card's question, and the line under the findings. */
function checkWords(answer: Summary): {
  view: ReturnType<typeof buildModelCheck>;
  question: string;
} | null {
  const check = answer.model_check;
  if (check === null) return null;
  const base = buildModelCheck(check);
  const { checked, notAsSet: found } = checkCounts(check);
  const rest = checked - found;
  const view = {
    ...base,
    okLine: found > 0 && rest > 0 ? tn("mc_ok_rest", rest) : base.okLine,
  };
  return { view, question: found > 0 ? tn("mc_sum_n", checked, { k: found }) : t("mc_q") };
}

export function SummaryCheckCard({ card }: { card: SummaryCard }) {
  const answer = card.answer;
  const title = t("rv_chk_h");
  if (answer === undefined) {
    if (card.error === null)
      return <ModelCheckLoading label={t("ld_line", { card: title.toLowerCase() })} />;
    return (
      <Card title={title} question={t("mc_q")} right={<HelpButton help="summary.modelcheck" />}>
        <CardError card={title} onRetry={card.retry} />
      </Card>
    );
  }
  const words = card.modelCheckError === null ? checkWords(answer) : null;
  if (words === null) {
    return (
      <Card title={title} question={t("mc_q")} right={<HelpButton help="summary.modelcheck" />}>
        {card.failed && <StaleLine updatedAt={card.updatedAt} />}
        <CardError card={title} onRetry={card.retry} />
      </Card>
    );
  }
  return (
    <ModelCheckCard
      help="summary.modelcheck"
      compact
      view={words.view}
      question={words.question}
      {...(card.failed ? { note: <StaleLine updatedAt={card.updatedAt} /> } : {})}
    />
  );
}

export function TopSessionsCard({
  card,
  project,
  range,
}: {
  card: SummaryCard;
  project: string;
  range: ReviewRange;
}) {
  const answer = card.answer;
  const title = t("rv_top_h");
  let body: React.ReactNode;
  let all: React.ReactNode = undefined;
  if (answer === undefined) {
    body =
      card.error === null ? (
        <CardBones card={title} rows={4} />
      ) : (
        <CardError card={title} onRetry={card.retry} />
      );
  } else {
    const rows = buildTopSessions(answer.top_sessions, answer.window.tz, answer.window.end);
    body = (
      <SessionsTable
        label={title}
        groups={[{ key: "top", label: "", rows }]}
        project={project}
        range={range}
      />
    );
    all = (
      <Button variant="quiet" href={`#${reviewPath(project, "sessions", range)}`}>
        {tn("top_all", answer.session_count)}
        <span aria-hidden="true">{" →"}</span>
      </Button>
    );
  }
  // The "?" keeps one place while the link to all sessions comes and goes.
  const right = (
    <span className="review-card-end">
      {all}
      <HelpButton help="summary.top" />
    </span>
  );
  return (
    <Card title={title} question={t("rv_top_q")} right={right}>
      {card.failed && <StaleLine updatedAt={card.updatedAt} />}
      {body}
    </Card>
  );
}
