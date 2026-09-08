/**
 * The section page over a running site: the API's note verbatim, the
 * provision target, the alias note, the section-number note, and the
 * compiled page's version picker and enacted link.
 */
import { expect, test } from "@playwright/test";

test("prints the API's note verbatim and renders the text", async ({ page }) => {
  const response = await page.goto("/app/us/pl/81/740/s3");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["cache-control"]).toBe("public, max-age=31536000, immutable");

  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator(".note")).toContainText(
    "This is section 3 of Public Law 81-740 as enacted on August 30, 1950 (64 Stat. 563). It is not updated.",
  );
  await expect(page.locator(".section-body .uslm-paragraph")).toHaveCount(8);
  await expect(page.locator(".section-body .uslm-sidenote").first()).toBeVisible();
  await expect(page.locator(".section-body a.uslm-page")).toHaveAttribute(
    "href",
    "https://www.govinfo.gov/link/statute/64/564",
  );
  await expect(page.locator(".neighbors a[rel=prev]")).toHaveAttribute("href", "/app/us/pl/81/740/s2");
  await expect(page.locator(".neighbors a[rel=next]")).toHaveAttribute("href", "/app/us/pl/81/740/s4");
});

test("the alias note on /us/act/…", async ({ page }) => {
  await page.goto("/app/us/act/1950-08-30/ch823/s3");
  await expect(page.locator(".note")).toContainText(
    "/us/act/1950-08-30/ch823/s3 is served as /us/pl/81/740/s3, the same law under its other identifier.",
  );
});

test("the section-number note on /us/pl/118/22/s101", async ({ page }) => {
  await page.goto("/app/us/pl/118/22/s101");
  await expect(page.locator(".note")).toContainText(
    "No unit is stored at /us/pl/118/22/s101; the section numbered 101 in this law is at /us/pl/118/22/dA/s101 and is served here.",
  );
  await expect(page.locator(".note")).toContainText(
    "This section has been amended since; the most recent law recorded is Public Law 118-35 (January 19, 2024).",
  );
  await expect(page.locator(".usa-breadcrumb")).toContainText("Division A");
});

test("a provision is marked inside its section", async ({ page }) => {
  await page.goto("/app/us/pl/118/5/dA/tI/s101/a");
  const target = page.locator(".section-body .target");
  await expect(target).toHaveCount(1);
  await expect(target).toHaveAttribute("id", "/us/pl/118/5/dA/tI/s101/a");
  await expect(page.locator(".section-body .target-path")).toHaveAttribute("id", "/us/pl/118/5/dA/tI/s101");
  await expect(page.getByText("is shown, marked, in the context of section 101")).toBeVisible();
  await expect(page.locator(".section-body blockquote.uslm-quotedContent").first()).toBeVisible();
});

test("a law with divisions lists its contents nested", async ({ page }) => {
  await page.goto("/app/us/pl/118/22");
  await expect(page.locator("h1")).toHaveText("Further Continuing Appropriations and Other Extensions Act, 2024");
  await expect(page.locator(".toc .toc a").first()).toBeVisible();
  await expect(page.locator(".toc a", { hasText: "Division A" })).toHaveAttribute("href", "/app/us/pl/118/22/dA");
  await expect(page.getByRole("heading", { name: "Cited by the US Code" })).toBeVisible();
});

test("the compiled page has a version picker and the enacted counterpart", async ({ page }) => {
  await page.goto("/app/us/sComp/83/703/tI/ch1./s1");
  await expect(page.locator(".note")).toContainText(
    "This is section 1 of Atomic Energy Act of 1954 as compiled by the House Office of the Legislative Counsel, incorporating amendments through Public Law 118-67 (July 9, 2024).",
  );
  await expect(page.locator(".versions a").first()).toHaveAttribute(
    "href",
    "/app/us/sComp/83/703/tI/ch1./s1?through=118-67",
  );
  await expect(page.locator(".facts a[href='/app/us/pl/83/703/s1']")).toBeVisible();
  await expect(page.locator(".section-body #\\/us\\/sComp\\/83\\/703\\/tI\\/ch1\\.\\/s1\\/a")).toBeVisible();
});

test("a 404 prints the API's detail with status 404", async ({ page }) => {
  const response = await page.goto("/app/us/pl/99/99999");
  expect(response?.status()).toBe(404);
  await expect(page.locator(".lede")).toHaveText(
    "nothing at /us/pl/99/99999 in the loaded Statutes at Large volumes",
  );
});
