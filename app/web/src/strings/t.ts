/*
 * Typed lookup over the string deck. A missing key or a missing placeholder is a compile error.
 * Call it with a literal key, t("nav_live"), so the static key test can see the call site.
 */
import { en } from "@/strings/en";

type Deck = typeof en;
type Key = keyof Deck;

type Placeholders<S extends string> = S extends `${string}{${infer P}}${infer Rest}`
  ? P | Placeholders<Rest>
  : never;

type ParamValue = string | number;
type ParamsFor<S extends string> = [Placeholders<S>] extends [never]
  ? [params?: undefined]
  : [params: Record<Placeholders<S>, ParamValue>];

/** Base names that have both a _one and an _other entry. */
type PluralBase = {
  [K in Key]: K extends `${infer B}_one` ? (`${B}_other` extends Key ? B : never) : never;
}[Key];

type PluralParamsFor<B extends PluralBase> =
  Exclude<Placeholders<Deck[`${B}_other` & Key]>, "n"> extends infer P extends string
    ? [P] extends [never]
      ? [params?: undefined]
      : [params: Record<P, ParamValue>]
    : never;

const plurals = new Intl.PluralRules("en");

function fill(template: string, params: Readonly<Record<string, ParamValue>> | undefined): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = params?.[name];
    return value === undefined ? whole : String(value);
  });
}

export function t<K extends Key>(key: K, ...args: ParamsFor<Deck[K]>): string {
  return fill(en[key], args[0]);
}

/** Plural lookup. The count fills {n}. English has one and other. */
export function tn<B extends PluralBase>(
  key: B,
  count: number,
  ...args: PluralParamsFor<B>
): string {
  const form = plurals.select(count) === "one" ? "one" : "other";
  const template: string = en[`${key}_${form}` as Key];
  const extra = args[0] as Readonly<Record<string, ParamValue>> | undefined;
  return fill(template, { ...extra, n: count });
}
