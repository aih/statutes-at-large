/** The front page names the latest laws loaded and when the sources were last checked. */
import { expect, test } from "@playwright/test";

test("the front page names the latest laws and the last check", async ({ page }) => {
  await page.goto("/app/");
  const latest = page.locator("dl.latest");
  await expect(latest.locator("dt", { hasText: "Public law" })).toBeVisible();
  await expect(latest.locator("dd a[href^='/app/us/pl/']")).toBeVisible();
  await expect(latest.locator("dt", { hasText: "Sources last checked" })).toBeVisible();
  await expect(latest).toContainText("GovInfo public-law bulk data");
});
