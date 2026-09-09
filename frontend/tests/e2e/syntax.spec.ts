/** The search syntax page documents the parser and links to search examples. */
import { expect, test } from "@playwright/test";

test("the syntax page lists heading: scope", async ({ page }) => {
  await page.goto("/app/search/syntax");
  await expect(page.locator("body")).toContainText("heading:");
});

test("the syntax page links to /app/search?q=", async ({ page }) => {
  await page.goto("/app/search/syntax");
  const links = await page.locator("a[href*='/app/search?q=']").all();
  expect(links.length).toBeGreaterThan(0);
});
