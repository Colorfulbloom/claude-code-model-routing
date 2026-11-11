import { SearchField } from "@/components/SearchField/SearchField";
import { Select, type SelectOption } from "@/components/Select/Select";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { tn, t } from "@/strings/t";
import { CONFIDENCE_WORDS } from "@/strings/lists";
import { en } from "@/strings/en";
import type { ConfidenceFilter } from "./rules-view";

export interface RulesToolsProps {
  q: string;
  onQ: (value: string) => void;
  confidence: ConfidenceFilter;
  onConfidence: (value: ConfidenceFilter) => void;
  /** Rules per Confidence word, or null while the rules load, when the Select shows no counts. */
  counts: Record<ConfidenceFilter, number> | null;
  /** The visible count and the polite announcement, or null while loading. */
  count: { text: string; announce: string } | null;
  /** False after a failed read, so the count bone does not wait for a number that will not come. */
  loading?: boolean;
}

/**
 * The tool row of How Claude Code decides: the search field with its count, and the Confidence
 * Select with the meaning of each word under it. While the rules load the Select shows no counts
 * and the count line is a bone. The field itself works from the first frame, and a q already in the
 * URL applies once the data arrives.
 */
export function RulesTools({
  q,
  onQ,
  confidence,
  onConfidence,
  counts,
  count,
  loading = true,
}: RulesToolsProps) {
  const number = (id: ConfidenceFilter): string =>
    counts === null ? "" : ` ${String(counts[id])}`;
  const items: SelectOption[] = [
    { id: "all", label: `${t("dc_conf_all")}${number("all")}` },
    ...CONFIDENCE_WORDS.map((item) => ({
      id: item.id,
      label: `${en[item.word]}${number(item.id)}`,
      description: en[item.means],
    })),
  ];
  return (
    <div className="ref-tools">
      <SearchField
        className="ref-search"
        label={t("dc_search_label")}
        value={q}
        onChange={onQ}
        clearLabel={t("sf_clear")}
        placeholder={t("dc_search_ph")}
        {...(count === null ? {} : { count: count.text, announce: count.announce })}
      />
      <Select
        className="ref-confidence"
        label={t("dc_conf_label")}
        items={items}
        value={confidence}
        onChange={(id) => {
          onConfidence(id as ConfidenceFilter);
        }}
      />
      {count === null && loading && (
        <SkeletonBones
          className="ref-count-bone"
          label={t("dc_loading")}
          bones={[{ width: "s" }]}
        />
      )}
    </div>
  );
}

/** The visible count and the announcement for a result. */
export function countWords(
  shown: number,
  total: number,
  narrowed: boolean,
): { text: string; announce: string } {
  if (!narrowed) {
    return { text: tn("dc_count", total), announce: tn("dc_count_ann", total) };
  }
  return {
    text: t("dc_count_of", { n: shown, total }),
    announce: shown === 0 ? t("dc_count_ann_none") : t("dc_count_ann_of", { n: shown, total }),
  };
}
