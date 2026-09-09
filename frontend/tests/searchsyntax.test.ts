import { describe, expect, it } from "vitest";

import { hasScope, highlightSnippet, toggleScope, withoutScope, withScope } from "../src/lib/search";

describe("highlightSnippet", () => {
  it("keeps the highlighter's <em> tags", () => {
    expect(highlightSnippet("the <em>rubber</em> industry")).toBe("the <em>rubber</em> industry");
  });

  it("escapes a <script> tag inside the underlying text", () => {
    expect(highlightSnippet("see <script>alert(1)</script> for details")).toBe(
      "see &lt;script&gt;alert(1)&lt;/script&gt; for details",
    );
  });

  it("escapes <script> beside a real <em> highlight", () => {
    expect(highlightSnippet("<em>rubber</em> <script>bad</script> and wood")).toBe(
      "<em>rubber</em> &lt;script&gt;bad&lt;/script&gt; and wood",
    );
  });

  it("escapes ampersands and quotes", () => {
    expect(highlightSnippet(`rubber & "wood" products`)).toBe("rubber &amp; &quot;wood&quot; products");
  });
});

describe("facet scope editing", () => {
  it("hasScope reads a scope word already in the query", () => {
    expect(hasScope("rubber congress:81", "congress", "81")).toBe(true);
    expect(hasScope("rubber congress:81", "congress", "82")).toBe(false);
  });

  it("withScope adds congress and kind as an OR — several values stay", () => {
    expect(withScope("rubber", "congress", "81")).toBe("rubber congress:81");
    expect(withScope("rubber congress:81", "congress", "82")).toBe("rubber congress:81 congress:82");
    expect(withScope("rubber congress:81", "congress", "81")).toBe("rubber congress:81");
  });

  it("withScope replaces view — the query carries at most one", () => {
    expect(withScope("rubber view:enacted", "view", "compiled")).toBe("rubber view:compiled");
    expect(withScope("rubber", "view", "compiled")).toBe("rubber view:compiled");
  });

  it("withoutScope removes one value and leaves the rest", () => {
    expect(withoutScope("rubber congress:81 congress:82", "congress", "81")).toBe("rubber congress:82");
    expect(withoutScope("rubber kind:pl", "kind", "pl")).toBe("rubber");
  });

  it("toggleScope adds when off and removes when on", () => {
    expect(toggleScope("rubber", "kind", "pl")).toBe("rubber kind:pl");
    expect(toggleScope("rubber kind:pl", "kind", "pl")).toBe("rubber");
  });

  it("keeps a quoted phrase intact while editing scopes", () => {
    expect(withScope('"wild horses"', "congress", "92")).toBe('"wild horses" congress:92');
  });
});
