/*
 * The states the two Reference pages share: the card for a link whose target is gone, and the
 * bones while the rules load. The page CSS is global, so every class carries the ref- prefix.
 */
import { useEffect, useId, useRef } from "react";
import { Button } from "@/components/Button/Button";
import { SkeletonBones, type Bone } from "@/components/SkeletonBones/SkeletonBones";
import { t } from "@/strings/t";

export interface GoneCardProps {
  /** The heading, such as "There's no rule called x". */
  title: string;
  /** The link to the whole list, and where it goes. */
  link: { label: string; href: string };
}

/**
 * The line for a stale key, rule id or term id. It says what is missing and offers the whole list.
 * Focus lands on the link, as it does on a setup item that left its part.
 */
export function GoneCard({ title, link }: GoneCardProps) {
  const headingId = useId();
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    // A microtask, so the route's own focus on the page heading, which runs after this effect when
    // the answer is already cached, does not take it back.
    queueMicrotask(() => {
      ref.current?.querySelector("a")?.focus();
    });
  }, []);
  return (
    <section ref={ref} className="card ref-gone" aria-labelledby={headingId}>
      <h2 className="ref-gone-title" id={headingId}>
        {title}
      </h2>
      <p>{t("sp_gone_b")}</p>
      <div>
        <Button href={link.href}>{link.label}</Button>
      </div>
    </section>
  );
}

/** Bones the height of the rows they stand for, with one spoken line. */
export function RuleBones({ rows }: { rows: number }) {
  const widths: Bone["width"][] = ["l", "m", "full", "m", "l"];
  const bones: Bone[] = Array.from({ length: rows }, (_, index) => ({
    width: widths[index % widths.length] ?? "m",
  }));
  return <SkeletonBones label={t("dc_loading")} bones={bones} className="ref-bones" />;
}
