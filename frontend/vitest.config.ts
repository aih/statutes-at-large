import { defineConfig } from "vitest/config";

/** Vitest over `src/lib`: the renderer, the reference rules, the URL helpers
 * and the labels client. The pages are covered by Playwright (`tests/e2e`),
 * which this config excludes. */
export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    exclude: ["tests/e2e/**", "node_modules/**"],
    environment: "node",
  },
});
