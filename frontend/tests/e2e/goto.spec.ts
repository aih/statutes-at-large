/** The citation box, with JavaScript off: the four outcomes of `/app/goto`. */
import { expect, test } from "@playwright/test";

test.use({ javaScriptEnabled: false });

const BOX = "header input[name=q]";

test("a loaded citation lands on its page", async ({ page }) => {
  await page.goto("/app/");
  await page.fill(BOX, "Pub. L. 81-740, § 3");
  await page.press(BOX, "Enter");
  await expect(page).toHaveURL(/\/app\/us\/pl\/81\/740\/s3$/u);
  await expect(page.locator("h1")).toContainText("Sec. 3");
});

test("a US Code citation is sent to the US Code site", async ({ request }) => {
  const response = await request.get("/app/goto?q=43%20U.S.C.%201701", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  expect(response.headers()["location"]).toBe("https://uscode.linkedlegislation.org/us/usc/t43/s1701");
});

test("a citation naming nothing loaded is a 404 with the note", async ({ page }) => {
  const response = await page.goto("/app/goto?q=999%20Stat.%201");
  expect(response?.status()).toBe(404);
  expect(response?.headers()["cache-control"]).toBe("private, no-store");
  await expect(page.locator(".usa-alert--warning")).toContainText(
    "999 Stat. 1 is /us/stat/999/1; no loaded law prints on that page.",
  );
  await expect(page.locator(".usa-alert--warning")).toContainText("/us/stat/999/1");
  await expect(page.locator("main input[name=q]")).toHaveValue("999 Stat. 1");
});

test("text that is not a citation redirects to search, the query prefilled", async ({ request, page }) => {
  const response = await request.get("/app/goto?q=garbage", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  expect(response.headers()["location"]).toBe("/app/search?q=garbage");

  await page.goto("/app/goto?q=garbage");
  await expect(page).toHaveURL(/\/app\/search\?q=garbage$/u);
  await expect(page.locator("header input[name=q]")).toHaveValue("garbage");
});
