/**
 * Copies USWDS's images into public/uswds/img, where `$theme-image-path`
 * points. Runs before `astro dev` and `astro build`; a no-op when the package
 * is absent (the production image installs without devDependencies and never
 * builds).
 */
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = fileURLToPath(new URL("../node_modules/@uswds/uswds/dist/img", import.meta.url));
const target = fileURLToPath(new URL("../public/uswds/img", import.meta.url));

if (existsSync(source)) {
  mkdirSync(target, { recursive: true });
  cpSync(source, target, { recursive: true });
}
