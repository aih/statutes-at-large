/** axe over one page of each kind: no violations against WCAG 2.1 AA. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const PAGES = [
  "/app/",
  "/app/us/pl/81/740",
  "/app/us/pl/81/740/s3",
  "/app/us/act/1950-08-30/ch823/s3",
  "/app/us/pl/118/22/s101",
  "/app/us/pl/118/5/dA/tI/s101/a",
  "/app/us/pl/118/22/dA",
  "/app/us/sComp/83/703/tI/ch1./s1",
  "/app/us/stat/137/112",
  "/app/goto?q=110%20Stat.%204196",
  "/app/goto?q=garbage",
  "/app/us/pl/99/99999",
];

for (const path of PAGES) {
  test(`${path} has no axe violations`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(
      results.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
    ).toEqual([]);
  });
}
