/** The sources page names the converters and links the example volume 1 page. */
import { expect, test } from "@playwright/test";

test("the sources page names both converters", async ({ page }) => {
  await page.goto("/app/sources");
  await expect(page.locator("body")).toContainText("Digitization Vendor");
  await expect(page.locator("body")).toContainText("GPO Locator to USLM Converter");
});

test("the footer links to the sources page", async ({ page }) => {
  await page.goto("/app/");
  await expect(page.locator("#site-footer a[href='/app/sources']")).toBeVisible();
});
