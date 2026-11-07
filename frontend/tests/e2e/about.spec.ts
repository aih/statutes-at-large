/** The About page and the footer name the author and the site's address. */
import { expect, test } from "@playwright/test";

test("the about page links to the author and the site", async ({ page }) => {
  await page.goto("/app/about");
  await expect(page.locator("main a[href='https://aih.github.io']")).toHaveText("Ari Hershowitz");
  await expect(page.locator("main a[href='https://statutes.linkedlegislation.org']")).toBeVisible();
});

test("the footer links to the about page and the author", async ({ page }) => {
  await page.goto("/app/");
  await expect(page.locator("#site-footer a[href='/app/about']")).toBeVisible();
  await expect(page.locator("#site-footer a[href='https://aih.github.io']")).toBeVisible();
});
