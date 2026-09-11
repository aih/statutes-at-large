/**
 * USLM → HTML, element for element, ported from the US Code site's
 * `frontend/src/lib/uslm.ts` (its ADR-0015) for the Statutes at Large and
 * Statute Compilation vocabulary.
 *
 * The rules: `@class` and `@style` are copied through; `@identifier` becomes
 * `id` on the first element that carries it; unknown elements become `div`;
 * `ref` is resolved through `refs.ts`; `sidenote` is an `aside`; `page` is an
 * inline marker linked to the govinfo page; the element whose identifier is
 * `target` is marked `target` and its ancestors `target-path`.
 */

import { DOMParser } from "@xmldom/xmldom";

import { resolveRef } from "./refs";
import type { Labels } from "./types";
import { govinfoStatute, parseStatPage } from "./url";

/** The members this module reads on an xmldom node. */
export interface UslmNode {
  nodeType: number;
  nodeValue: string | null;
  childNodes: ArrayLike<UslmNode>;
  previousSibling?: UslmNode | null;
  nextSibling?: UslmNode | null;
}

export interface UslmElement extends UslmNode {
  tagName: string;
  localName: string | null;
  getAttribute(name: string): string | null;
}

const ELEMENT_NODE = 1;
const TEXT_NODE = 3;

export function parseFragment(xml: string): UslmElement {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  return doc.documentElement as unknown as UslmElement;
}

/** The `<slice>` children of a `<statPage>` root, in document order — one per
 * document of a Statutes at Large page (B2). Neither `statPage` nor `slice`
 * carries an `@identifier`, and neither is in the element map below, so each
 * renders as a plain `div` container; `slice`'s own children are the law's
 * USLM between the page's markers. */
export function sliceElements(root: UslmElement): UslmElement[] {
  const found: UslmElement[] = [];
  for (let i = 0; i < root.childNodes.length; i++) {
    const node = root.childNodes[i];
    if (node.nodeType === ELEMENT_NODE && tagOf(node as UslmElement) === "slice") found.push(node as UslmElement);
  }
  return found;
}

/** `smallCaps` when the root's own `heading` carries that class, else null.
 * The page's h1 prints the heading from the API, which has no classes. */
export function titleClass(root: UslmElement): string | null {
  for (let i = 0; i < root.childNodes.length; i++) {
    const node = root.childNodes[i];
    if (node.nodeType !== ELEMENT_NODE || tagOf(node as UslmElement) !== "heading") continue;
    const classes = ((node as UslmElement).getAttribute("class") ?? "").split(/\s+/u);
    return classes.includes("smallCaps") ? "smallCaps" : null;
  }
  return null;
}

/** Every `ref/@href` in the fragment, in document order. */
export function hrefs(fragment: UslmElement): string[] {
  const found: string[] = [];
  walk(fragment, (el) => {
    if (tagOf(el) === "ref") {
      const href = el.getAttribute("href");
      if (href) found.push(href);
    }
  });
  return found;
}

function walk(el: UslmElement, visit: (el: UslmElement) => void): void {
  visit(el);
  for (let i = 0; i < el.childNodes.length; i++) {
    const child = el.childNodes[i];
    if (child.nodeType === ELEMENT_NODE) walk(child as UslmElement, visit);
  }
}

function tagOf(el: UslmElement): string {
  return el.localName ?? el.tagName;
}

/** Containers that carry a `<heading>` of their own; entering one is a step
 * down the outline, and every one below the root is a rung of the ladder. */
const LEVEL_TAGS = new Set([
  "division",
  "subdivision",
  "title",
  "subtitle",
  "chapter",
  "subchapter",
  "part",
  "subpart",
  "article",
  "subarticle",
  "section",
  "subsection",
  "paragraph",
  "subparagraph",
  "clause",
  "subclause",
  "item",
  "subitem",
  "level",
]);

/** Body text at a leaf. A `div`, not a `p`: in this vocabulary `content` and
 * `chapeau` hold `sidenote`, `quotedContent` and `page` elements. */
const PROSE_TAGS = new Set(["content", "continuation", "proviso", "chapeau"]);

/** Inline formatting and inline vocabulary: never a block. */
const INLINE_TAGS: Record<string, string> = {
  i: "i",
  b: "b",
  sub: "sub",
  sup: "sup",
  span: "span",
  inline: "span",
  a: "span",
  date: "span",
  footnote: "span",
  shortTitle: "span",
  amendingAction: "span",
  quotedText: "span",
  term: "span",
  designator: "span",
  label: "span",
  column: "span",
};

/** Block containers of this vocabulary, rendered as `div` with their class. */
const BLOCK_TAGS = new Set([
  "toc",
  "referenceItem",
  "layout",
  "header",
  "row",
  "longTitle",
  "enrolledDateline",
  "action",
  "signatures",
  "preamble",
  "editorialNote",
  "note",
  "notes",
  "sourceCredit",
]);

/** Elements that end a sentence when they appear inside one: a `quotedContent`
 * holding any of these is a block quotation whatever surrounds it. */
const BLOCK_CHILD_TAGS = new Set([...LEVEL_TAGS, ...PROSE_TAGS, "toc", "p", "table", "heading", "sidenote", "layout"]);

const TABLE_TAGS: Record<string, string> = {
  table: "table",
  caption: "caption",
  thead: "thead",
  tbody: "tbody",
  tr: "tr",
  td: "td",
  th: "th",
  colgroup: "colgroup",
  col: "col",
};

/** Document apparatus that never belongs in a rendered fragment. */
const SKIP_TAGS = new Set(["meta", "property", "docNumber", "docPublicationName", "dc:title"]);

export interface RenderOptions {
  /** The identifier the URL named below the section: marked `target`, its
   * ancestors `target-path`. */
  target: string | null;
  labels: Labels;
}

interface State {
  opts: RenderOptions;
  /** Elements on the path from the root to the target. */
  path: Set<UslmElement>;
  /** Identifiers already stamped as `id`; a repeat gets none. */
  ids: Set<string>;
}

/** Renders the fragment's root element and everything under it. */
export function render(fragment: UslmElement, opts: RenderOptions): string {
  const state: State = { opts, path: targetPath(fragment, opts.target), ids: new Set() };
  return renderElement(fragment, state, 0);
}

/** The ancestors of the element whose identifier is `target`, the root
 * included and the target excluded. */
function targetPath(root: UslmElement, target: string | null): Set<UslmElement> {
  const path = new Set<UslmElement>();
  if (!target) return path;
  const stack: UslmElement[] = [];
  let found = false;
  const visit = (el: UslmElement): void => {
    if (found) return;
    if (el.getAttribute("identifier") === target) {
      for (const ancestor of stack) path.add(ancestor);
      found = true;
      return;
    }
    stack.push(el);
    for (let i = 0; i < el.childNodes.length && !found; i++) {
      const child = el.childNodes[i];
      if (child.nodeType === ELEMENT_NODE) visit(child as UslmElement);
    }
    stack.pop();
  };
  visit(root);
  return path;
}

function inRunningProse(el: UslmElement): boolean {
  const filled = (node: UslmNode | null | undefined): boolean =>
    node?.nodeType === TEXT_NODE && (node.nodeValue ?? "").trim() !== "";
  return filled(el.previousSibling) || filled(el.nextSibling);
}

function hasBlockChild(el: UslmElement): boolean {
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType !== ELEMENT_NODE) continue;
    if (BLOCK_CHILD_TAGS.has(tagOf(node as UslmElement))) return true;
  }
  return false;
}

function hasBlockDescendant(el: UslmElement): boolean {
  let found = false;
  walk(el, (child) => {
    if (child !== el && (tagOf(child) === "sidenote" || tagOf(child) === "quotedContent" || tagOf(child) === "table")) {
      found = true;
    }
  });
  return found;
}

function renderElement(el: UslmElement, state: State, depth: number): string {
  const tag = tagOf(el);
  if (tag.includes(":") || SKIP_TAGS.has(tag)) return "";

  const elDepth = LEVEL_TAGS.has(tag) ? depth + 1 : depth;

  if (tag === "heading") {
    const level = Math.min(Math.max(depth + 1, 2), 6);
    return wrapTag(`h${level}`, el, state, elDepth, ["uslm-heading"]);
  }
  if (tag === "ref") return renderRef(el, state);
  if (tag === "sidenote") return wrapTag("aside", el, state, elDepth, ["uslm-sidenote"], { role: "note" });
  if (tag === "page") return renderPage(el, state);
  if (tag === "quotedContent") {
    if (!hasBlockChild(el) && inRunningProse(el)) {
      return wrapTag("span", el, state, elDepth, ["uslm-quotedContent", "uslm-inlined"]);
    }
    return wrapTag("blockquote", el, state, elDepth, ["uslm-quotedContent"]);
  }
  if (tag === "br") return "<br/>";
  if (tag === "table") return renderTable(el, state, elDepth);
  if (tag in TABLE_TAGS) return wrapTag(TABLE_TAGS[tag], el, state, elDepth, [`uslm-${tag}`]);
  if (tag in INLINE_TAGS) return wrapTag(INLINE_TAGS[tag], el, state, elDepth, [`uslm-${tag}`]);
  if (tag === "num") return wrapTag("span", el, state, elDepth, ["uslm-num"]);
  if (tag === "p") {
    // A `p` holding a sidenote or a quotation cannot be an HTML `p`.
    const htmlTag = hasBlockDescendant(el) ? "div" : "p";
    return wrapTag(htmlTag, el, state, elDepth, ["uslm-p"]);
  }
  if (PROSE_TAGS.has(tag)) return wrapTag("div", el, state, elDepth, [`uslm-${tag}`]);
  if (BLOCK_TAGS.has(tag)) return wrapTag("div", el, state, elDepth, [`uslm-${tag}`]);

  // Every level below the root is a rung: `prov` is what the stylesheet
  // indents. Anything else this table does not name is a `div`.
  const ladder = LEVEL_TAGS.has(tag) && depth > 0 ? ["prov"] : [];
  return wrapTag("div", el, state, elDepth, [`uslm-${tag}`, ...ladder]);
}

function renderTable(el: UslmElement, state: State, depth: number): string {
  const table = wrapTag("table", el, state, depth, ["uslm-table"]);
  const label = captionText(el) || "Table";
  return `<div class="uslm-tablewrap" role="region" tabindex="0" aria-label="${escapeAttr(label)}">${table}</div>`;
}

function captionText(table: UslmElement): string {
  for (let i = 0; i < table.childNodes.length; i++) {
    const node = table.childNodes[i];
    if (node.nodeType !== ELEMENT_NODE) continue;
    const child = node as UslmElement;
    if (tagOf(child) === "caption") return normalizeSpace(inlineText(child));
  }
  return "";
}

function renderChildren(el: UslmElement, state: State, depth: number): string {
  let out = "";
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType === ELEMENT_NODE) {
      out += renderElement(node as UslmElement, state, depth);
    } else if (node.nodeType === TEXT_NODE) {
      out += escapeText(node.nodeValue ?? "");
    }
  }
  return out;
}

function attributesOf(el: UslmElement, state: State, extraClasses: string[], extra: Record<string, string> = {}): string {
  const identifier = el.getAttribute("identifier");
  const classes = [...extraClasses];
  const sourceClass = el.getAttribute("class");
  if (sourceClass) classes.push(sourceClass);
  if (identifier && identifier === state.opts.target) classes.push("target");
  if (state.path.has(el)) classes.push("target-path");

  const attrs = [`class="${escapeAttr(classes.join(" "))}"`];
  if (identifier && !state.ids.has(identifier)) {
    state.ids.add(identifier);
    attrs.push(`id="${escapeAttr(identifier)}"`);
  }
  const style = el.getAttribute("style");
  if (style) attrs.push(`style="${escapeAttr(style)}"`);
  for (const [name, value] of Object.entries(extra)) {
    attrs.push(`${name}="${escapeAttr(value)}"`);
  }
  return attrs.join(" ");
}

function wrapTag(
  htmlTag: string,
  el: UslmElement,
  state: State,
  childDepth: number,
  extraClasses: string[],
  extra: Record<string, string> = {},
): string {
  const attrs = attributesOf(el, state, extraClasses, extra);
  const inner = renderChildren(el, state, childDepth);
  return `<${htmlTag} ${attrs}>${inner}</${htmlTag}>`;
}

/** A page marker: `<page identifier="/us/stat/64/564">64 Stat. 564</page>`,
 * an inline link to the govinfo page when the identifier names one. */
function renderPage(el: UslmElement, state: State): string {
  const identifier = el.getAttribute("identifier") ?? "";
  const text = normalizeSpace(inlineText(el)) || identifier;
  const page = parseStatPage(identifier);
  const inner = escapeText(text);
  if (page) {
    const attrs = attributesOf(el, state, ["uslm-page"], { href: govinfoStatute(page.volume, page.page) });
    return `<a ${attrs}>${inner}</a>`;
  }
  const attrs = attributesOf(el, state, ["uslm-page"]);
  return `<span ${attrs}>${inner}</span>`;
}

function renderRef(el: UslmElement, state: State): string {
  const href = el.getAttribute("href") ?? "";
  const resolved = resolveRef(href, state.opts.labels);
  const text = renderChildren(el, state, 0);
  if (!resolved.href) {
    return `<cite class="uslm-ref uslm-ref--plain">${text}</cite>`;
  }
  const title = resolved.title ? ` title="${escapeAttr(resolved.title)}"` : "";
  const external = /^https?:\/\//u.test(resolved.href);
  const classes = external ? "uslm-ref usa-link usa-link--external" : "uslm-ref";
  return `<a class="${classes}" href="${escapeAttr(resolved.href)}"${title}>${text}</a>`;
}

function inlineText(el: UslmElement): string {
  let out = "";
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType === TEXT_NODE) {
      out += node.nodeValue ?? "";
    } else if (node.nodeType === ELEMENT_NODE) {
      const child = node as UslmElement;
      const tag = tagOf(child);
      if (tag.includes(":") || SKIP_TAGS.has(tag)) continue;
      out += inlineText(child);
    }
  }
  return out;
}

function normalizeSpace(value: string): string {
  return value.replace(/\s+/gu, " ").trim();
}

export function escapeHtml(value: string): string {
  return value.replace(/&/gu, "&amp;").replace(/</gu, "&lt;").replace(/>/gu, "&gt;");
}

function escapeText(value: string): string {
  return escapeHtml(value);
}

function escapeAttr(value: string): string {
  return escapeText(value).replace(/"/gu, "&quot;");
}
