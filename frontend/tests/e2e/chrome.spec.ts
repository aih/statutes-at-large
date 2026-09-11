/**
 * The sticky header, the rail, the Contents disclosure, and the top/bottom
 * links, over the widths the plan names: 375, 700 (part of the header's
 * measurement, not asserted on here) and 1280.
 */
import { expect, test } from "@playwright/test";

const WIDTHS = [375, 1280] as const;

for (const width of WIDTHS) {
  test(`sticky header at ${width}px: target below header after a fragment jump`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/app/us/pl/81/740/s3#about-h");

    const headerBox = await page.locator(".site-header").boundingBox();
    const targetBox = await page.locator("h2#about-h").boundingBox();
    expect(headerBox).toBeTruthy();
    expect(targetBox).toBeTruthy();
    expect(targetBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height - 1);
  });

  test(`sticky header at ${width}px: stays at the top after scrolling`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/app/us/pl/81/740/s3");
    await page.evaluate(() => window.scrollBy(0, 800));

    const headerBox = await page.locator(".site-header").boundingBox();
    expect(headerBox).toBeTruthy();
    expect(headerBox!.y).toBe(0);
  });

  test(`end links are visible at ${width}px, with 44px targets`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/app/us/pl/81/740/s3");

    const top = page.locator(".end-links__link--top");
    const bottom = page.locator(".end-links__link--bottom");
    await expect(bottom).toBeVisible();
    for (const link of [top, bottom]) {
      const box = await link.boundingBox();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
  });
}

test("end links do not overlap the footer's text at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/app/us/pl/81/740/s3");
  await page.locator("#site-footer").scrollIntoViewIfNeeded();

  const linksBox = await page.locator(".end-links").boundingBox();
  const textBox = await page.locator(".site-footer__inner p").boundingBox();
  expect(linksBox).toBeTruthy();
  expect(textBox).toBeTruthy();
  const overlaps =
    linksBox!.x < textBox!.x + textBox!.width &&
    linksBox!.x + linksBox!.width > textBox!.x &&
    linksBox!.y < textBox!.y + textBox!.height &&
    linksBox!.y + linksBox!.height > textBox!.y;
  expect(overlaps).toBe(false);
});

test("site footer has the required id", async ({ page }) => {
  await page.goto("/app/us/pl/81/740/s3");
  await expect(page.locator("#site-footer")).toBeVisible();
});

test("the footer carries the version and commit line", async ({ page }) => {
  await page.goto("/app/us/pl/81/740/s3");
  const text = await page.locator(".site-footer__version").innerText();
  expect(text).toContain("version 0.1.0");
  expect(text).toContain("commit");
});

test("the rail is visible at 1280px, beside the text", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/app/us/pl/81/740/s3");

  const rail = page.locator(".rail");
  await expect(rail).toBeVisible();
  const railBox = await rail.boundingBox();
  const colBox = await page.locator(".reader-col").boundingBox();
  expect(railBox!.x).toBeLessThan(colBox!.x);
});

test("the rail is stacked after the text at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("/app/us/pl/81/740/s3");

  const rail = page.locator(".rail");
  const order = await rail.evaluate((el) => getComputedStyle(el).order);
  expect(order).toBe("2");
  const railBox = await rail.boundingBox();
  const colBox = await page.locator(".reader-col").boundingBox();
  expect(railBox!.y).toBeGreaterThan(colBox!.y + colBox!.height - 1);
});

test("the rail marks the section being read", async ({ page }) => {
  await page.goto("/app/us/pl/81/740/s3");
  await expect(page.locator('.rail__link[aria-current="page"]')).toHaveText(/Sec\. 3/);
});

test("the Contents disclosure is open by default on a law page and a hierarchy node", async ({ page }) => {
  await page.goto("/app/us/pl/111/240");
  const contents = page.locator("details#contents");
  await expect(contents).toHaveCount(1);
  await expect(contents).toHaveJSProperty("open", true);
  await expect(contents.locator("summary")).toContainText("Contents —");
  await page.goto("/app/us/pl/111/344/tI");
  await expect(contents).toHaveJSProperty("open", true);
  await expect(contents.locator("summary")).toContainText("Contents —");
});

test("a #contents fragment jump opens the disclosure", async ({ page }) => {
  await page.goto("/app/us/pl/111/240#contents");
  await page.waitForFunction(() => document.querySelector("details#contents")?.hasAttribute("open"));
  await expect(page.locator("details#contents")).toHaveJSProperty("open", true);
});

test("the Pages disclosure prints open on a section page", async ({ page }) => {
  await page.goto("/app/us/pl/81/740/s3");
  await expect(page.locator("details#pages")).toHaveJSProperty("open", true);
});
