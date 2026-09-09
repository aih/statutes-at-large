/** The Statutes at Large page: its documents, the PDF link, and the unit the marker falls in. */
import { expect, test } from "@playwright/test";

test("lists the documents on the page", async ({ page }) => {
  const response = await page.goto("/app/us/stat/137/112");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["cache-control"]).toBe("public, max-age=300");
  await expect(page.locator("h1")).toHaveText("137 Stat. 112");
  await expect(page.locator("a[href='https://www.govinfo.gov/link/statute/137/112']")).toBeVisible();
  const row = page.locator(".toc a[href='/app/us/pl/118/22']");
  await expect(row).toContainText("Public Law 118-22");
  await expect(row).toContainText("starts on this page");
});

test("names the unit the page marker falls in", async ({ page }) => {
  await page.goto("/app/us/stat/64/564");
  await expect(page.locator(".toc a[href='/app/us/pl/81/740']")).toContainText("continues onto this page");
  await expect(page.locator("a[href='/app/us/pl/81/740/s3']")).toBeVisible();
});

test("a page nothing prints on is the API's 404", async ({ page }) => {
  const response = await page.goto("/app/us/stat/999/1");
  expect(response?.status()).toBe(404);
  await expect(page.locator(".lede")).toContainText("nothing at /us/stat/999/1");
});
