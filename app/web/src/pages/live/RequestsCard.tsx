/* Latest requests: five rows of the eight the server sends, and the price footer. */
import { Card } from "@/components/Card/Card";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { TableWell } from "@/components/TableWell/TableWell";
import type { TableColumn, TableRowData } from "@/components/TableWell/TableWell";
import type { RequestRow } from "@/lib/live-tiles";
import { dateWords } from "@/lib/clock";
import { t } from "@/strings/t";

const columns: TableColumn[] = [
  { id: "time", name: t("rq_time"), rowHeader: true },
  { id: "agent", name: t("rq_agent") },
  { id: "model", name: t("rq_model"), hp: true },
  { id: "tokens", name: t("rq_tokens"), align: "end" },
  { id: "cost", name: t("rq_cost"), align: "end" },
];

export interface PriceFacts {
  /** The price table's date, "2026-11-08". */
  asOf: string;
  /** The model the second price source disagrees on, or null when the sources agree. */
  disagree: string | null;
}

export function RequestsCard({
  rows,
  prices,
  loading = false,
}: {
  rows: RequestRow[];
  prices: PriceFacts | null;
  loading?: boolean;
}) {
  const tableRows: TableRowData[] = rows.map((row) => ({
    id: row.id,
    cells: {
      time: row.time,
      agent: row.agent,
      model: (
        <>
          {row.model !== null && <ModelSwatch model={row.model} />}
          {row.modelLabel}
        </>
      ),
      tokens: row.tokens,
      cost: row.cost,
    },
  }));
  return (
    <Card title={t("rq_h")} question={t("rq_q")}>
      <TableWell
        label={t("rq_h")}
        columns={columns}
        rows={tableRows}
        {...(loading ? { loading: { label: "" } } : {})}
      />
      {prices !== null && (
        <div className="live-rq-foot">
          <p>{`${t("rq_f_est")} ${t("rq_f_prices", { date: dateWords(prices.asOf) })}.`}</p>
          <p>{t("rq_f_sub")}</p>
          {prices.disagree !== null && (
            <p className="live-rq-warn">
              <span aria-hidden="true">{"▲ "}</span>
              {t("rq_f_disagree", { model: prices.disagree })}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
