/**
 * Two pure functions the search results page needs and nothing else does:
 * escaping a snippet for `set:html` while keeping the highlighter's `<em>`,
 * and editing a query string to add or remove a facet.
 *
 * Facet-link editing is written here rather than built from the query
 * string the API's `facets` field carries, because the API's `facets` are
 * counts (`{value, count}`), not query fragments — there is nothing in the
 * response to build a link from except the query the reader already has.
 * `hasScope`, `withScope` and `withoutScope` mirror `with_filter` and
 * `without_filter` in `storage/searchquery.py`, narrowed to the three scope
 * words a facet produces (`congress`, `kind`, `view`); `law`, `year`, `vol`
 * and `heading` are not facets and are not handled here.
 */

/** `<em>` and `</em>` survive; every other character that could open a tag
 * or an attribute is escaped. A snippet's underlying text is GPO's OCR, not
 * markup, so anything else shaped like a tag is data, not a script the
 * highlighter meant to keep. */
export function highlightSnippet(snippet: string): string {
  const escaped = snippet.replace(/[&<>"']/gu, (ch) => ESCAPES[ch]);
  return escaped.replace(/&lt;(\/?em)&gt;/gu, "<$1>");
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** The scope words a facet link can carry. `SCOPE_FIELDS` in
 * `storage/searchquery.py` has more (`law`, `year`, `vol`, `heading`); only
 * these three come back as `facets`. */
export type FacetScope = "congress" | "kind" | "view";

/** Whitespace-separated tokens, except a double-quoted run is one token —
 * mirrors `_TOKENS` in `storage/searchquery.py`. */
const TOKENS = /[a-zA-Z]+:"[^"]*"|"[^"]*"|\S+/gu;
const SCOPE_TOKEN = /^([a-zA-Z]+):(.*)$/u;

function unquote(value: string): string {
  return value.length >= 2 && value.startsWith('"') && value.endsWith('"') ? value.slice(1, -1) : value;
}

function quoteIfSpaced(value: string): string {
  return value.includes(" ") ? `"${value}"` : value;
}

interface ScopeTerm {
  name: string;
  value: string;
}

function tokenize(q: string): { rest: string[]; scopes: ScopeTerm[] } {
  const rest: string[] = [];
  const scopes: ScopeTerm[] = [];
  for (const token of q.match(TOKENS) ?? []) {
    const match = SCOPE_TOKEN.exec(token);
    if (!match) {
      rest.push(token);
      continue;
    }
    const value = unquote(match[2]).trim();
    if (!value) {
      rest.push(token);
      continue;
    }
    scopes.push({ name: match[1].toLowerCase(), value });
  }
  return { rest, scopes };
}

function unparse(rest: string[], scopes: ScopeTerm[]): string {
  const parts = [...rest];
  for (const { name, value } of scopes) parts.push(`${name}:${quoteIfSpaced(value)}`);
  return parts.join(" ");
}

/** Whether the query already carries `name:value`. */
export function hasScope(q: string, name: FacetScope, value: string): boolean {
  return tokenize(q).scopes.some((s) => s.name === name && s.value === value);
}

/**
 * The same query with `name:value` added. `congress` and `kind` are an OR
 * over several values, so a second value of the same scope is added beside
 * the first; `view` is single-valued in the query (`ParsedQuery.view`), so
 * a new value there replaces whatever `view:` was already written, matching
 * `with_filter`'s `replace(parsed, view=stored)`.
 */
export function withScope(q: string, name: FacetScope, value: string): string {
  if (hasScope(q, name, value)) return q;
  const { rest, scopes } = tokenize(q);
  const kept = name === "view" ? scopes.filter((s) => s.name !== "view") : scopes;
  return unparse(rest, [...kept, { name, value }]);
}

/** The same query with `name:value` removed. */
export function withoutScope(q: string, name: FacetScope, value: string): string {
  const { rest, scopes } = tokenize(q);
  return unparse(
    rest,
    scopes.filter((s) => !(s.name === name && s.value === value)),
  );
}

/** Add the scope, or remove it if it is already on — what a facet link does. */
export function toggleScope(q: string, name: FacetScope, value: string): string {
  return hasScope(q, name, value) ? withoutScope(q, name, value) : withScope(q, name, value);
}
