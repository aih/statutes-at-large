/**
 * The browser suite (`make test-e2e`), run over a site that is already up:
 * `BASE_URL`, default `http://localhost:4321` (the dev server). It is not part
 * of `make test`.
 */
import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:4321";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: 0,
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
  ],
});
