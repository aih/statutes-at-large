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

/**
 * The browser's address as the adapter reports it (`Astro.clientAddress`: the
 * leftmost `X-Forwarded-For`, which the proxy sets to the peer it trusts, or
 * the socket peer). Null where the adapter cannot say, so a call without it
 * still goes out.
 */
export function clientAddressOf(astro: { clientAddress: string }): string | null {
  try {
    const address = astro.clientAddress;
    return address && address.trim() !== "" ? address : null;
  } catch {
    return null;
  }
}
