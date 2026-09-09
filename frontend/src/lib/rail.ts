/**
 * What the rail's "In this law" list shows (C2). `Rail.astro` calls
 * `railNodes` on the page's nested table of contents; the pure function is
 * tested on its own in `tests/rail.test.ts`.
 */

import type { TocLike, TocNode } from "./toc";

export interface RailNode {
  entry: TocLike;
  children: RailNode[];
  /** Whether this node's own `<details>` starts open. Meaningful only when
   * `children` is non-empty; a leaf section renders no `<details>` and
   * ignores it. */
  open: boolean;
}

function countAll(nodes: TocNode[]): number {
  let total = 0;
  for (const node of nodes) total += 1 + countAll(node.children);
  return total;
}

function onPath(node: TocNode, current: string | null): boolean {
  if (!current) return false;
  return node.entry.identifier === current || current.startsWith(`${node.entry.identifier}/`);
}

/** Every node, nested in full; `open` marks the branch holding `current`. */
function fullTree(nodes: TocNode[], current: string | null): RailNode[] {
  return nodes.map((node) => ({
    entry: node.entry,
    open: onPath(node, current),
    children: fullTree(node.children, current),
  }));
}

/**
 * Hierarchy nodes always; a section only where its parent branch is open.
 * A closed hierarchy node carries no children at all, so a law with
 * thousands of units puts only the open branch's sections into the page.
 */
function boundedTree(nodes: TocNode[], current: string | null): RailNode[] {
  const out: RailNode[] = [];
  for (const node of nodes) {
    if (node.entry.is_section) {
      out.push({ entry: node.entry, open: false, children: [] });
      continue;
    }
    const open = onPath(node, current);
    out.push({ entry: node.entry, open, children: open ? boundedTree(node.children, current) : [] });
  }
  return out;
}

/**
 * What the rail lists: every node when the law holds at most `limit` units
 * in all; otherwise the hierarchy skeleton plus the branch holding `current`.
 */
export function railNodes(toc: TocNode[], current: string | null, limit = 300): RailNode[] {
  return countAll(toc) <= limit ? fullTree(toc, current) : boundedTree(toc, current);
}
