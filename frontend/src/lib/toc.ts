/**
 * Tables of contents: nesting a reading-order list by identifier prefix,
 * finding a section's neighbours, and labelling a unit.
 */

import type { Link } from "./types";
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

/** A unit's link text: its label and its heading when it has one. */
export function unitLinkText(entry: { level: string; num: string | null; heading: string | null }): string {
  const label = unitLabel(entry.level, entry.num);
  return entry.heading ? `${label} ${entry.heading}`.trim() : label || entry.heading || "";
}

/** The sections before and after `identifier` among the `is_section`
 * entries, as links; null at either end or when it is not in the list. */
export function sectionNeighbors(
  entries: TocLike[],
  identifier: string,
): { previous: Link | null; next: Link | null } {
  const sections = entries.filter((entry) => entry.is_section);
  const at = sections.findIndex((entry) => entry.identifier === identifier);
  const link = (entry: TocLike | undefined): Link | null =>
    entry ? { href: appHref(entry.identifier), label: unitLinkText(entry) } : null;
  if (at === -1) return { previous: null, next: null };
  return { previous: link(sections[at - 1]), next: link(sections[at + 1]) };
}
