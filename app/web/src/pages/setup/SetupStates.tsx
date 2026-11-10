/*
 * The states Your setup and the surface pages share: the error with Try again, the line that says a
 * refresh failed while the last good answer stays on screen, and the bones while the first answer is
 * on its way. Their classes carry the setup- prefix, because page CSS is global (fact J-0ba9).
 */
import { Button } from "@/components/Button/Button";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import type { Bone } from "@/components/SkeletonBones/SkeletonBones";
import { clockShort } from "@/lib/clock";
import { t } from "@/strings/t";

/** "Couldn't load what shapes a session", with the one button that asks again. */
export function SetupError({ card, onRetry }: { card: string; onRetry: () => void }) {
  return (
    <RaisedFinding
      variant="error"
      title={t("er_h", { card: card.toLowerCase() })}
      className="setup-error"
      actions={<Button onPress={onRetry}>{t("er_try")}</Button>}
    >
      <p>{t("er_b")}</p>
    </RaisedFinding>
  );
}

/** "Updated 6:41 PM. The latest refresh failed." Shown only while a refetch fails. */
export function SetupStale({ receivedAt }: { receivedAt: number | null }) {
  if (receivedAt === null) return null;
  return <p className="setup-stale">{t("cd_stale", { time: clockShort(receivedAt) })}</p>;
}

/** Bones the height of the rows they stand for, with one spoken line. */
export function SetupBones({ line, rows = 4 }: { line: string; rows?: number }) {
  const bones: Bone[] = Array.from({ length: rows }, () => ({ width: "full" }));
  return <SkeletonBones label={line} bones={bones} />;
}
