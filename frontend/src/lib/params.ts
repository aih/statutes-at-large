/** A route parameter as an identifier path: decoded once, trailing slashes dropped. */
export function identifierParam(prefix: string, param: string | undefined): string {
  const raw = (param ?? "").replace(/\/+$/u, "");
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    decoded = raw;
  }
  return decoded ? `${prefix}/${decoded}` : prefix;
}
