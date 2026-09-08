// @ts-check
import { fileURLToPath } from "node:url";

import node from "@astrojs/node";
import { defineConfig } from "astro/config";

/**
 * The reader at /app (design stage 5; the US Code site's ADR-0011 and 0015).
 *
 * `base: "/app"` is the contract with the proxy: Caddy sends /app/* here and
 * everything else to FastAPI. `output: "server"` because every page is built
 * from a live API call. The dev proxy sends the API's paths to
 * `API_BASE_URL` so `npm run dev` is a whole site on one origin.
 */
const API = process.env.API_BASE_URL ?? "http://localhost:8001";

export default defineConfig({
  base: "/app",
  trailingSlash: "ignore",
  output: "server",
  adapter: node({ mode: "standalone" }),
  server: { port: 4321, host: true },
  devToolbar: { enabled: false },
  vite: {
    css: {
      preprocessorOptions: {
        scss: {
          loadPaths: [
            fileURLToPath(new URL("./node_modules/@uswds/uswds/packages", import.meta.url)),
          ],
          quietDeps: true,
          silenceDeprecations: ["import", "global-builtin", "mixed-decls"],
        },
      },
    },
    server: {
      // The dev server strips `base` before the proxy sees a URL, so a request
      // that began with `/app/` is left to Astro whatever path remains.
      proxy: Object.fromEntries(
        ["/api/v1", "/health", "/docs", "/openapi.json"].map((path) => [
          `^${path}`,
          {
            target: API,
            changeOrigin: true,
            bypass(req) {
              if (req.originalUrl && req.originalUrl.startsWith("/app/")) {
                return req.url;
              }
            },
          },
        ]),
      ),
    },
  },
});
