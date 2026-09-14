/**
 * Tables of contents: nesting a reading-order list by identifier prefix,
 * finding a section's neighbours, and labelling a unit.
 */

import type { Link, TocEntry } from "./types";
import { appHref } from "./url";

export interface TocLike {
  identifier: string;
  level: string;
  num: string | null;
  heading: string | null;
  is_section: boolean;
}

export interface TocNode {
  entry: TocLike;
  children: TocNode[];
}

/** Nests a reading-order list: an entry is a child of the nearest earlier
 * entry whose identifier is a prefix of its own. */
export function nestToc(entries: TocLike[]): TocNode[] {
  const roots: TocNode[] = [];
  const stack: TocNode[] = [];
  for (const entry of entries) {
    const node: TocNode = { entry, children: [] };
    while (stack.length > 0 && !entry.identifier.startsWith(`${stack[stack.length - 1].entry.identifier}/`)) {
      stack.pop();
    }
    (stack.length > 0 ? stack[stack.length - 1].children : roots).push(node);
    stack.push(node);
  }
  return roots;
}

const LEVEL_WORDS: Record<string, string> = {
  division: "Division",
  subdivision: "Subdivision",
  title: "Title",
  subtitle: "Subtitle",
  chapter: "Chapter",
  subchapter: "Subchapter",
  part: "Part",
  subpart: "Subpart",
  article: "Article",
  subarticle: "Subarticle",
  section: "Sec.",
  law: "",
  compilation: "",
};

/** `("title", "I")` → `Title I`; `("section", "101")` → `Sec. 101`. */
export function unitLabel(level: string, num: string | null): string {
  const word = LEVEL_WORDS[level] ?? level.charAt(0).toUpperCase() + level.slice(1);
  const parts = [word, num ?? ""].filter((part) => part !== "");
  return parts.join(" ");
}

/** The one section a law or a hierarchy node holds: its only child when that
 * is a section, or the only section in a public law's toc. Null otherwise. */
export function onlySection(children: TocEntry[], summary: { section_count: number; toc: TocEntry[] } | null): TocEntry | null {
  if (children.length === 1 && children[0].is_section) return children[0];
  if (summary?.section_count === 1) return summary.toc.find((entry) => entry.is_section) ?? null;
  return null;
}

/** `smallCaps` for a heading that has lower-case letters and no capitals,
 * else undefined. The volume and PLAW USLM type a small-caps heading in lower
 * case (`<heading class="smallCaps">elimination of …</heading>`); the API's
 * `heading` is that text without the class. */
export function smallCapsClass(heading: string | null | undefined): "smallCaps" | undefined {
  return heading && /\p{Ll}/u.test(heading) && !/\p{Lu}/u.test(heading) ? "smallCaps" : undefined;
}

/** A section link: `label` is the unit label, `heading` the heading printed after it. */
export interface SectionLink extends Link {
  heading: string | null;
}

/** The sections before and after `identifier` among the `is_section`
 * entries, as links; null at either end or when it is not in the list. */
export function sectionNeighbors(
  entries: TocLike[],
  identifier: string,
): { previous: SectionLink | null; next: SectionLink | null } {
  const sections = entries.filter((entry) => entry.is_section);
  const at = sections.findIndex((entry) => entry.identifier === identifier);
  const link = (entry: TocLike | undefined): SectionLink | null =>
    entry ? { href: appHref(entry.identifier), label: unitLabel(entry.level, entry.num), heading: entry.heading } : null;
  if (at === -1) return { previous: null, next: null };
  return { previous: link(sections[at - 1]), next: link(sections[at + 1]) };
}
