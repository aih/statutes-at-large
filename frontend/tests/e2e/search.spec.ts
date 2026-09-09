/** `/app/search` over the dev stack with the fixture volumes indexed. */
import { expect, test } from "@playwright/test";

test("a word search returns results with a linked law label and a highlighted snippet", async ({ page }) => {
  await page.goto("/app/search?q=rubber");
  await expect(page.locator("h1")).toContainText("Search");
  await expect(page.locator("h2.group").first()).toContainText(/result/u);

  const first = page.locator(".searchresult").first();
  await expect(first).toBeVisible();
  const lawLink = first.locator("p.toc__meta a").first();
  await expect(lawLink).toHaveAttribute("href", /^\/app\/us\/(pl|pvtl|act)\//u);
  await expect(first.locator("em").first()).toBeVisible();
});

test("the note is printed verbatim", async ({ page }) => {
  await page.goto("/app/search?q=rubber");
  await expect(page.locator(".note")).toContainText("Results are the sections and headings of the laws as enacted.");
});

test("zero results prints the syntax link and the citation forms", async ({ page }) => {
  await page.goto("/app/search?q=zzzznoresultsforthissearchxyz");
  await expect(page.locator("h2.group")).toContainText("No results");
  await expect(page.locator("a[href='/app/search/syntax']")).toBeVisible();
  await expect(page.locator("a", { hasText: "43 U.S.C. 1701" })).toBeVisible();
});

test("a query with nothing to search for is a 400 with the detail", async ({ page }) => {
  const response = await page.goto("/app/search?q=view%3Acompiled");
  expect(response?.status()).toBe(400);
  await expect(page.locator("body")).toContainText("that query has nothing to search for");
});

test("the sort control marks the current order and links the others", async ({ page }) => {
  await page.goto("/app/search?q=rubber");
  await expect(page.locator("[aria-label='Sort results'] [aria-current]")).toHaveText("Relevance");
  const dateLink = page.locator("[aria-label='Sort results'] a", { hasText: "Date" });
  await dateLink.click();
  await expect(page).toHaveURL(/[?&]sort=date/u);
  await expect(page.locator("[aria-label='Sort results'] [aria-current]")).toHaveText("Date");
});

test("the view control marks enacted current by default", async ({ page }) => {
  await page.goto("/app/search?q=rubber");
  await expect(page.locator("[aria-label='Filter by view'] [aria-current]")).toHaveText("Enacted");
});

test("a congress facet link narrows the query and marks itself current", async ({ page }) => {
  await page.goto("/app/search?q=rubber");
  const facet = page.locator("#facets a").first();
  const label = (await facet.textContent())?.trim() ?? "";
  await facet.click();
  await expect(page).toHaveURL(/congress%3A|congress:/u);
  const active = page.locator("#facets a[aria-current='true']").first();
  await expect(active).toHaveText(label);
});

test("the goto box redirects a non-citation here with the query prefilled", async ({ page }) => {
  await page.goto("/app/goto?q=rubber+industry");
  await expect(page).toHaveURL(/\/app\/search\?q=/u);
  await expect(page.locator("header input[name=q]")).toHaveValue("rubber industry");
});
