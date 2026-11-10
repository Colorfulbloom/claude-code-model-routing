/*
 * The states a Review card shares: its error (with Try again), the line that says a refresh failed
 * while the last good answer stays on screen, and the bones while the first answer is on its way.
 */
import { Button } from "@/components/Button/Button";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import type { Bone } from "@/components/SkeletonBones/SkeletonBones";
import { clockShort } from "@/lib/clock";
import { t } from "@/strings/t";

/** "Couldn't load cost per day", with the one button that asks again. */
export function CardError({ card, onRetry }: { card: string; onRetry: () => void }) {
  return (
    <RaisedFinding
      variant="error"
      title={t("er_h", { card: card.toLowerCase() })}
      className="review-error"
      actions={<Button onPress={onRetry}>{t("er_try")}</Button>}
    >
      <p>{t("er_b")}</p>
    </RaisedFinding>
  );
}

/** "Updated 6:41 PM. The latest refresh failed." Shown only while a refetch fails. */
export function StaleLine({ updatedAt }: { updatedAt: number | null }) {
  if (updatedAt === null) return null;
  return <p className="review-stale">{t("cd_stale", { time: clockShort(updatedAt) })}</p>;
}

/** Bones the height of the rows they stand for. `card` names what loads, for the spoken line. */
export function CardBones({
  card,
  rows = 4,
  className,
}: {
  card: string;
  rows?: number;
  className?: string;
}) {
  const bones: Bone[] = Array.from({ length: rows }, () => ({ width: "full" }));
  return (
    <SkeletonBones
      label={t("ld_line", { card: card.toLowerCase() })}
      bones={bones}
      {...(className !== undefined ? { className } : {})}
    />
  );
}
