/**
 * Every keyboard shortcut the reader has, in one list (ADR-0022).
 *
 * The list is data because two things need it and they must not disagree:
 * `ShortcutsDialog.astro` renders it, and `KeyboardNav.astro`'s island
 * receives the key-to-action map out of it as JSON. An `is:inline` script
 * can import nothing, so the alternative was a second copy of the bindings
 * written into the script, which is how a documented shortcut stops being
 * the shortcut that fires.
 *
 * Ported from the US Code site's `lib/shortcuts.ts` (its ADR-0055) with
 * this site's actions. No Alt, Ctrl or ⌘ binding: this site has one box
 * and no page commands, so there is nothing for a held modifier to reach.
 *
 * `keys` is what the reader sees and `codes` is what `KeyboardEvent.key`
 * reports; they differ for the arrows and for `?` and `Esc`.
 */

export interface Shortcut {
  /** What the island does. One `switch` arm each, in `KeyboardNav.astro`,
   * except `previous-section`, `next-section` and `up-level` (a page
   * navigation looked up in `targets`) and `close` (the dialog's own). */
  action: string;
  /** As printed in the help dialog. */
  keys: string[];
  /** As `KeyboardEvent.key` reports them. */
  codes: string[];
  /** The sentence in the help dialog. Imperative, no trailing stop. */
  what: string;
}

export interface ShortcutGroup {
  name: string;
  /** True when every shortcut in the group needs a section on screen. The
   * dialog says so, rather than listing keys that do nothing on the page
   * the reader is looking at. */
  sectionOnly?: boolean;
  items: Shortcut[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    name: "Moving between sections",
    sectionOnly: true,
    items: [
      { action: "previous-section", keys: ["←", "j"], codes: ["ArrowLeft", "j"], what: "Previous section" },
      { action: "next-section", keys: ["→", "k"], codes: ["ArrowRight", "k"], what: "Next section" },
      { action: "previous-provision", keys: ["["], codes: ["["], what: "Previous top-level provision" },
      { action: "next-provision", keys: ["]"], codes: ["]"], what: "Next top-level provision" },
      { action: "about", keys: ["a"], codes: ["a"], what: "About this text" },
    ],
  },
  {
    name: "Moving around a unit",
    items: [
      { action: "up-level", keys: ["u"], codes: ["u"], what: "Up to the nearest ancestor, or the law" },
      { action: "contents", keys: ["c"], codes: ["c"], what: "The contents" },
      { action: "pages", keys: ["p"], codes: ["p"], what: "The Statutes at Large pages" },
      { action: "versions", keys: ["v"], codes: ["v"], what: "Versions, on a compiled page" },
    ],
  },
  {
    name: "Anywhere on the site",
    items: [
      { action: "top", keys: ["t"], codes: ["t"], what: "Top of the page" },
      { action: "bottom", keys: ["b"], codes: ["b"], what: "Bottom of the page" },
      { action: "search", keys: ["/"], codes: ["/"], what: "The citation box" },
      { action: "help", keys: ["?"], codes: ["?"], what: "This list" },
      { action: "close", keys: ["Esc"], codes: ["Escape"], what: "Close this list" },
    ],
  },
];

/** `{ "ArrowLeft": "previous-section", "?": "help", … }` — what the island
 * switches on.
 *
 * Built here so the bindings are derived from the printed list rather than
 * written twice. A key claimed by two actions is a bug the dialog cannot
 * show, so it throws rather than letting the later one win silently. */
export function keyMap(): Record<string, string> {
  const map: Record<string, string> = {};
  for (const group of SHORTCUT_GROUPS) {
    for (const item of group.items) {
      for (const code of item.codes) {
        if (map[code]) {
          throw new Error(`Two actions bound to ${code}: ${map[code]} and ${item.action}`);
        }
        map[code] = item.action;
      }
    }
  }
  return map;
}
