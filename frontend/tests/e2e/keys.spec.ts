/**
 * The keyboard shortcuts (D, ADR-0022), over a running site.
 *
 * Vitest (`shortcuts.test.ts`) covers the data: that the map is derivable
 * and that every printed action has a `switch` arm. This file is the rest:
 * whether a key actually fires in a browser, where the scroll position and
 * the keyboard focus end up, and that a key typed into the citation box is
 * left alone.
 */
import { expect, test } from "@playwright/test";

/** A section with eight top-level provisions and a neighbour on either side. */
const SECTION = "/app/us/pl/81/740/s3";
/** A section with an ancestor above the law, for `u`. */
const NESTED_SECTION = "/app/us/pl/118/22/dA/s101";
/** A compiled section, for `v`. */
const COMPILED_SECTION = "/app/us/sComp/83/703/tI/ch1./s1";

const focusedId = (page: import("@playwright/test").Page) => page.evaluate(() => document.activeElement?.id || "");

/** Waits for a smooth scroll to finish rather than guessing its duration. */
async function settled(page: import("@playwright/test").Page): Promise<number> {
  const scrollY = () => page.evaluate(() => Math.round(window.scrollY));
  let last = -1;
  for (let i = 0; i < 40; i += 1) {
    const now = await scrollY();
    if (now === last) return now;
    last = now;
    await page.waitForTimeout(100);
  }
  return last;
}

test("k moves to the next section", async ({ page }) => {
  await page.goto(SECTION);
  await page.keyboard.press("k");
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740\/s4$/u);
});

test("j moves to the previous section", async ({ page }) => {
  await page.goto("/app/us/pl/81/740/s4");
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740\/s3$/u);
});

test("] steps onto the first provision, then the second", async ({ page }) => {
  await page.goto(SECTION);
  await page.keyboard.press("]");
  await settled(page);
  expect(await focusedId(page)).toBe("/us/pl/81/740/s3/1");

  await page.keyboard.press("]");
  await settled(page);
  expect(await focusedId(page)).toBe("/us/pl/81/740/s3/2");
});

test("[ steps back to the provision before it", async ({ page }) => {
  await page.goto(SECTION);
  await page.keyboard.press("]");
  await page.keyboard.press("]");
  await settled(page);
  await page.keyboard.press("[");
  await settled(page);
  expect(await focusedId(page)).toBe("/us/pl/81/740/s3/1");
});

test("[ and ] say why they did nothing on a section with no provisions", async ({ page }) => {
  await page.goto("/app/us/pl/118/3/s1");
  const said = page.locator("#keysay");
  await expect(said).toBeEmpty();
  await page.keyboard.press("]");
  await expect(said).toHaveText(/no provisions to step through/u);
});

test("u goes up to the nearest ancestor", async ({ page }) => {
  await page.goto(NESTED_SECTION);
  await page.keyboard.press("u");
  await expect(page).toHaveURL(/\/app\/us\/pl\/118\/22\/dA$/u);
});

test("u does nothing on the law page, which has no ancestor", async ({ page }) => {
  await page.goto("/app/us/pl/81/740");
  await page.keyboard.press("u");
  await page.waitForTimeout(300);
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740$/u);
});

test("a reaches About this text", async ({ page }) => {
  await page.goto(SECTION);
  await page.keyboard.press("a");
  await settled(page);
  expect(await focusedId(page)).toBe("about-h");
});

test("p opens the pages disclosure", async ({ page }) => {
  await page.goto("/app/us/pl/81/740");
  await page.keyboard.press("p");
  await settled(page);
  await expect(page.locator("details#pages")).toHaveJSProperty("open", true);
});

test("v reaches Versions on a compiled page", async ({ page }) => {
  await page.goto(COMPILED_SECTION);
  await page.keyboard.press("v");
  await settled(page);
  expect(await focusedId(page)).toBe("versions");
});

test("t and b reach the top and the bottom", async ({ page }) => {
  await page.goto(SECTION);
  await page.evaluate(() => window.scrollTo(0, 800));
  await page.keyboard.press("t");
  await settled(page);
  expect(await focusedId(page)).toBe("main");

  await page.keyboard.press("b");
  await settled(page);
  expect(await focusedId(page)).toBe("site-footer");
});

test("/ focuses the citation box", async ({ page }) => {
  await page.goto(SECTION);
  await page.keyboard.press("/");
  await expect(page.locator("#cite-q")).toBeFocused();
});

test("a key typed into the citation box is left alone", async ({ page }) => {
  await page.goto(SECTION);
  await page.keyboard.press("/");
  await page.keyboard.type("junk");
  await expect(page.locator("#cite-q")).toHaveValue("junk");
  // j, k and u are all bound. None of them fired while typing.
  await expect(page).toHaveURL(/s3$/u);
});

test("? opens the shortcut list, and Escape closes it", async ({ page }) => {
  await page.goto(SECTION);
  const dialog = page.locator("#shortcuts");
  await expect(dialog).toBeHidden();

  await page.keyboard.press("Shift+Slash");
  await expect(dialog).toBeVisible();
  expect(
    await page.evaluate(() => document.querySelector("#shortcuts")!.contains(document.activeElement)),
  ).toBe(true);

  // Nothing behind the modal answers a key while it is open.
  const before = await page.evaluate(() => Math.round(window.scrollY));
  await page.keyboard.press("]");
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(before);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("the footer link opens the dialog rather than navigating", async ({ page }) => {
  await page.goto(SECTION);
  await page.locator("footer [data-shortcuts-open]").click();
  await expect(page.locator("#shortcuts")).toBeVisible();
  await expect(page).toHaveURL(/s3$/u);
});

test("? is available on a page with no section", async ({ page }) => {
  await page.goto("/app/");
  await page.keyboard.press("Shift+Slash");
  await expect(page.locator("#shortcuts")).toBeVisible();
});

test("c reaches the rail when it is pinned beside the text", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(SECTION);
  await page.keyboard.press("c");
  await settled(page);
  expect(await page.evaluate(() => document.activeElement?.className || "")).toContain("rail");
});

test("the section-only keys do nothing on the law page", async ({ page }) => {
  await page.goto("/app/us/pl/81/740");
  for (const key of ["j", "k", "a", "[", "]"]) {
    await page.keyboard.press(key);
  }
  await page.waitForTimeout(300);
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740$/u);
});
