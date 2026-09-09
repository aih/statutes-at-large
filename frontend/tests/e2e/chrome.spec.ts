/** The sticky header and top/bottom links over two widths. */
import { expect, test } from "@playwright/test";

test("measure header height at 375px", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  if (headerBox) {
    const rem = (headerBox.height / 16).toFixed(3);
    console.log(`Header height at 375px: ${headerBox.height}px = ${rem}rem`);
  }

  await context.close();
});

test("measure header height at 700px", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 700, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  if (headerBox) {
    const rem = (headerBox.height / 16).toFixed(3);
    console.log(`Header height at 700px: ${headerBox.height}px = ${rem}rem`);
  }

  await context.close();
});

test("measure header height at 1280px", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  if (headerBox) {
    const rem = (headerBox.height / 16).toFixed(3);
    console.log(`Header height at 1280px: ${headerBox.height}px = ${rem}rem`);
  }

  await context.close();
});

test("sticky header at 375px: target below header after jump", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3#about-h");

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  const target = page.locator("h2#about-h");
  const targetBox = await target.boundingBox();
  expect(targetBox).toBeTruthy();

  // The target's top should be at or below the header's bottom edge.
  if (headerBox && targetBox) {
    expect(targetBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height - 1);
  }

  await context.close();
});

test("sticky header at 1280px: target below header after jump", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3#about-h");

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  const target = page.locator("h2#about-h");
  const targetBox = await target.boundingBox();
  expect(targetBox).toBeTruthy();

  // The target's top should be at or below the header's bottom edge.
  if (headerBox && targetBox) {
    expect(targetBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height - 1);
  }

  await context.close();
});

test("sticky header at 375px: stays at top after scroll", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  // Scroll down a bit.
  await page.evaluate(() => window.scrollBy(0, 800));

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  // Header should still be at the top.
  if (headerBox) {
    expect(headerBox.y).toBe(0);
  }

  await context.close();
});

test("sticky header at 1280px: stays at top after scroll", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  // Scroll down a bit.
  await page.evaluate(() => window.scrollBy(0, 800));

  const header = page.locator(".site-header");
  const headerBox = await header.boundingBox();
  expect(headerBox).toBeTruthy();

  // Header should still be at the top.
  if (headerBox) {
    expect(headerBox.y).toBe(0);
  }

  await context.close();
});

test("end links are visible at 375px", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  const endLink = page.locator(".end-links__link--bottom");
  await expect(endLink).toBeVisible();

  await context.close();
});

test("end links are visible at 1280px", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("/app/us/pl/81/740/s3");

  const endLink = page.locator(".end-links__link--bottom");
  await expect(endLink).toBeVisible();

  await context.close();
});

test("site footer has the required id", async ({ page }) => {
  await page.goto("/app/us/pl/81/740/s3");
  const footer = page.locator("#site-footer");
  await expect(footer).toBeVisible();
});
