/** The Statutes at Large page: its slice, the "Read … in full" links, the
 * neighbours, and the documents list. */
import { expect, test } from "@playwright/test";

test("lists the documents on the page", async ({ page }) => {
  const response = await page.goto("/app/us/stat/137/112");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["cache-control"]).toBe("public, max-age=300");
  await expect(page.locator("h1")).toHaveText("137 Stat. 112");
  await expect(page.locator(".doc-meta a[href='https://www.govinfo.gov/link/statute/137/112']")).toBeVisible();
  const row = page.locator(".toc a[href='/app/us/pl/118/22']");
  await expect(row).toContainText("Public Law 118-22");
  await expect(row).toContainText("starts on this page");
});

test("renders the slice and names the unit the page marker falls in", async ({ page }) => {
  await page.goto("/app/us/stat/64/564");

  // The reworded documents list: the law began on an earlier page.
  const row = page.locator(".toc a[href='/app/us/pl/81/740']");
  await expect(row).toContainText("begins at 64 Stat. 563 and prints on this page");

  // "Text on this page": the "Begins inside …" line and the "Read … in full" link.
  await expect(page.locator("#text")).toHaveText("Text on this page");
  await expect(page.locator(".doc-meta", { hasText: "Begins inside Sec. 3" })).toBeVisible();
  const readInFull = page.locator("a", { hasText: "Read section 3 in full" });
  await expect(readInFull).toHaveAttribute("href", "/app/us/pl/81/740/s3");
  await expect(page.locator("a", { hasText: "Read section 4 in full" })).toHaveAttribute(
    "href",
    "/app/us/pl/81/740/s4",
  );

  // The rendered USLM: section 4's text and its sidenote.
  await expect(page.locator("article.section-body")).toContainText("The corporation shall have power");
  await expect(page.locator(".uslm-sidenote")).toContainText("Powers.");

  // The numeric neighbours.
  await expect(page.locator(".neighbors a[href='/app/us/stat/64/563']")).toContainText("64 Stat. 563");
  await expect(page.locator(".neighbors a[href='/app/us/stat/64/565']")).toContainText("64 Stat. 565");
});

test("a page nothing prints on is the API's 404", async ({ page }) => {
  const response = await page.goto("/app/us/stat/999/1");
  expect(response?.status()).toBe(404);
  await expect(page.locator(".lede")).toContainText("nothing at /us/stat/999/1");
});

test("a lettered page has no arithmetic neighbour", async ({ page }) => {
  await page.goto("/app/us/stat/64/a12");
  await expect(page.locator(".neighbors")).toHaveCount(0);
});
