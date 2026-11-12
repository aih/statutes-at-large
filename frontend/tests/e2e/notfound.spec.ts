/** The reader's 404: the path, close links, the citation box and the site's pages. */
import { expect, test } from "@playwright/test";

test("a path the reader has no route for is a 404 that offers the page spelled closest", async ({ page }) => {
  const response = await page.goto("/app/abuot");
  expect(response?.status()).toBe(404);
  expect(response?.headers()["cache-control"]).toBe("private, no-store");
  await expect(page.locator("h1")).toHaveText("Page not found");
  await expect(page.locator(".lede")).toHaveText("There is no page at /app/abuot.");
  await expect(page.locator(".notfound__suggest a")).toHaveAttribute("href", "/app/about");
  await expect(page.locator(".notfound__pages a")).toHaveCount(9);
});

test("an identifier written without /us is offered with it", async ({ page }) => {
  await page.goto("/app/pl/81/740/s3");
  await page.locator(".notfound__suggest a").first().click();
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740\/s3$/u);
});

test("a law number in the path is offered as the law", async ({ page }) => {
  await page.goto("/app/81-740");
  await expect(page.locator(".notfound__suggest a").first()).toHaveText("Public Law 81-740");
});

test("a reader page in another letter case is a 301 to it", async ({ request }) => {
  const response = await request.get("/app/About", { maxRedirects: 0 });
  expect(response.status()).toBe(301);
  expect(response.headers()["location"]).toBe("/app/about");
});

test("a Congress number that is not one is the 404 page for that path", async ({ page }) => {
  const response = await page.goto("/app/congress/abc");
  expect(response?.status()).toBe(404);
  await expect(page.locator(".lede")).toHaveText("There is no page at /app/congress/abc.");
});

test("the citation box on the 404 goes to the citation", async ({ page }) => {
  await page.goto("/app/nothing-here");
  await page.fill("main input[name=q]", "Pub. L. 81-740, § 3");
  await page.press("main input[name=q]", "Enter");
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740\/s3$/u);
});

test("a law the API has no record of offers its Congress", async ({ page }) => {
  const response = await page.goto("/app/us/pl/99/99999");
  expect(response?.status()).toBe(404);
  await expect(page.locator(".notfound__suggest a")).toHaveAttribute("href", "/app/congress/99");
});
