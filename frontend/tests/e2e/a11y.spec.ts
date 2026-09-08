/** axe over the section page and the front page: no violations against WCAG 2.1 AA. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

for (const path of ["/app/us/pl/81/740/s3", "/app/us/pl/118/5/dA/tI/s101/a", "/app/"]) {
  test(`${path} has no axe violations`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(
      results.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
    ).toEqual([]);
  });
}
