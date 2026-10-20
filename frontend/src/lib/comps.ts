/**
 * The compilations index (`/app/comps`): each file's printed name, its sort
 * key and letter, the A–Z groups, and the word filter. Pure; tested in
 * `tests/comps.test.ts`.
 */

import type { CompTitle } from "./types";

/** The display title, else the official title, else the prefix. */
export function compName(comp: CompTitle): string {
  return comp.display_title ?? comp.title ?? comp.identifier_prefix;
}

/** The name without leading punctuation or quotation marks, for sorting and grouping. */
function sortName(comp: CompTitle): string {
  return compName(comp).replace(/^[^\p{L}\p{N}]+/u, "");
}

/** `A` to `Z` for a name starting with a letter, `#` otherwise. */
export function compLetter(comp: CompTitle): string {
  const first = sortName(comp).charAt(0).normalize("NFD").charAt(0).toUpperCase();
  return /^[A-Z]$/u.test(first) ? first : "#";
}

/** Every word of `q` appears in the name, the official title, the prefix or
 * the package id, ignoring case. An empty `q` matches everything. */
export function compMatches(comp: CompTitle, q: string): boolean {
  const words = q.toLowerCase().split(/\s+/u).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = [comp.display_title, comp.title, comp.identifier_prefix, comp.package_id].join(" ").toLowerCase();
  return words.every((word) => haystack.includes(word));
}

export interface CompGroup {
  letter: string;
  comps: CompTitle[];
}

/** The files grouped by letter, `#` first then A to Z, each group sorted by
 * name with numbers compared as numbers. */
export function groupComps(comps: CompTitle[]): CompGroup[] {
  const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });
  const sorted = [...comps].sort(
    (a, b) => collator.compare(sortName(a), sortName(b)) || collator.compare(a.file_id, b.file_id),
  );
  const groups = new Map<string, CompTitle[]>();
  for (const comp of sorted) {
    const letter = compLetter(comp);
    const group = groups.get(letter);
    if (group) group.push(comp);
    else groups.set(letter, [comp]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === "#" ? -1 : b === "#" ? 1 : a.localeCompare(b)))
    .map(([letter, items]) => ({ letter, comps: items }));
}
