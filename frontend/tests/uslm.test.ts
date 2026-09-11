import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import type { Labels } from "../src/lib/types";
import { hrefs, parseFragment, render, sliceElements, titleClass } from "../src/lib/uslm";

const NS = 'xmlns="http://schemas.gpo.gov/xml/uslm"';

function fixture(name: string): string {
  return readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8");
}

function html(xml: string, target: string | null = null, labels: Labels = {}): string {
  return render(parseFragment(xml), { target, labels });
}

describe("the element map", () => {
  it("renders levels as div with their class and a rung below the root", () => {
    const xml = `<section ${NS} identifier="/us/pl/1/1/s1"><subsection identifier="/us/pl/1/1/s1/a"><num>(a)</num><content>text</content></subsection></section>`;
    const out = html(xml);
    expect(out).toContain('<div class="uslm-section" id="/us/pl/1/1/s1">');
    expect(out).toContain('<div class="uslm-subsection prov" id="/us/pl/1/1/s1/a">');
    expect(out).toContain('<span class="uslm-num">(a)</span>');
    expect(out).toContain('<div class="uslm-content">text</div>');
  });

  it("gives headings a depth-tracking hN", () => {
    const xml = `<section ${NS}><heading>Top</heading><subsection><heading>Mid</heading><paragraph><heading>Leaf</heading></paragraph></subsection></section>`;
    const out = html(xml);
    expect(out).toContain('<h2 class="uslm-heading">Top</h2>');
    expect(out).toContain('<h3 class="uslm-heading">Mid</h3>');
    expect(out).toContain('<h4 class="uslm-heading">Leaf</h4>');
  });

  it("copies @class and @style through", () => {
    const xml = `<section ${NS} class="firstIndent1 fontsize10" style="-uslm-lc:I1"><num value="3"><inline class="smallCaps">Sec</inline>. 3.</num></section>`;
    const out = html(xml);
    expect(out).toContain('class="uslm-section firstIndent1 fontsize10"');
    expect(out).toContain('style="-uslm-lc:I1"');
    expect(out).toContain('<span class="uslm-inline smallCaps">Sec</span>');
  });

  it("renders unknown elements as div", () => {
    const xml = `<section ${NS}><enrolledDateline>Approved</enrolledDateline></section>`;
    expect(html(xml)).toContain('<div class="uslm-enrolledDateline">Approved</div>');
  });

  it("keeps quotedText, amendingAction, shortTitle and date inline", () => {
    const xml = `<section ${NS}><content>by <amendingAction type="delete">striking</amendingAction> “<quotedText>and</quotedText>” on <date date="2023-06-03">June 3</date> (<shortTitle>Act</shortTitle>)</content></section>`;
    const out = html(xml);
    for (const tag of ["amendingAction", "quotedText", "date", "shortTitle"]) {
      expect(out).toContain(`<span class="uslm-${tag}"`);
      expect(out).not.toContain(`<div class="uslm-${tag}"`);
    }
  });

  it("renders a quotedContent holding levels as a blockquote even beside text", () => {
    const xml = `<section ${NS}><content>the following:<quotedContent><paragraph><num>“(9)</num><content>x</content></paragraph></quotedContent>.</content></section>`;
    const out = html(xml);
    expect(out).toContain('<blockquote class="uslm-quotedContent">');
    expect(out).toContain("</blockquote>.");
  });

  it("keeps a quoted phrase inside a sentence inline", () => {
    const xml = `<section ${NS}><content>by striking <quotedContent>and</quotedContent> each place</content></section>`;
    const out = html(xml);
    expect(out).not.toContain("<blockquote");
    expect(out).toContain('<span class="uslm-quotedContent uslm-inlined">and</span>');
  });

  it("renders a table with table tags inside a focusable region", () => {
    const xml = `<section ${NS}><table><tr><td>a</td></tr></table></section>`;
    const out = html(xml);
    expect(out).toContain('<div class="uslm-tablewrap" role="region" tabindex="0" aria-label="Table">');
    expect(out).toContain("<table");
    expect(out).toContain("<td");
  });

  it("drops meta and namespaced elements", () => {
    const xml = `<section ${NS} xmlns:dc="http://purl.org/dc/elements/1.1/"><meta><dc:title>x</dc:title></meta><content>kept</content></section>`;
    const out = html(xml);
    expect(out).not.toContain("uslm-meta");
    expect(out).toContain("kept");
  });

  it("renders a p as div when it holds a sidenote", () => {
    const xml = `<section ${NS}><p>text<sidenote><p>note</p></sidenote></p><p>plain</p></section>`;
    const out = html(xml);
    expect(out).toContain('<div class="uslm-p">text<aside');
    expect(out).toContain('<p class="uslm-p">plain</p>');
  });

  it("escapes text and attributes", () => {
    const xml = `<section ${NS} class="a&quot;b"><content>1 &lt; 2 &amp; 3</content></section>`;
    const out = html(xml);
    expect(out).toContain('class="uslm-section a&quot;b"');
    expect(out).toContain("1 &lt; 2 &amp; 3");
  });
});

describe("identifiers and the target", () => {
  it("stamps @identifier as id on the first element carrying it only", () => {
    const xml = `<section ${NS} identifier="/us/pl/1/1/s1"><subsection identifier="/us/pl/1/1/s1/a"><content>one</content></subsection><subsection identifier="/us/pl/1/1/s1/a"><content>again</content></subsection></section>`;
    const out = html(xml);
    expect(out.match(/id="\/us\/pl\/1\/1\/s1\/a"/gu)).toHaveLength(1);
  });

  it("marks the target and its ancestors", () => {
    const xml = `<section ${NS} identifier="/us/pl/1/1/s1"><subsection identifier="/us/pl/1/1/s1/a"><paragraph identifier="/us/pl/1/1/s1/a/1"><content>x</content></paragraph></subsection><subsection identifier="/us/pl/1/1/s1/b"><content>y</content></subsection></section>`;
    const out = html(xml, "/us/pl/1/1/s1/a/1");
    expect(out).toContain('class="uslm-paragraph prov target"');
    expect(out).toContain('class="uslm-subsection prov target-path" id="/us/pl/1/1/s1/a"');
    expect(out).toContain('class="uslm-section target-path" id="/us/pl/1/1/s1"');
    expect(out).toContain('class="uslm-subsection prov" id="/us/pl/1/1/s1/b"');
  });

  it("marks nothing when the target is absent", () => {
    const xml = `<section ${NS} identifier="/us/pl/1/1/s1"><subsection identifier="/us/pl/1/1/s1/a"><content>x</content></subsection></section>`;
    const out = html(xml, "/us/pl/1/1/s1/z");
    expect(out).not.toContain("target");
  });
});

describe("references", () => {
  const labels: Labels = {
    "/us/pl/81/740/s3": {
      exists: true,
      served_identifier: "/us/pl/81/740/s3",
      resolution: "exact",
      num: "3",
      heading: null,
      level: "section",
      kind: "pl",
      law_identifier: "/us/pl/81/740",
      law_label: "Public Law 81-740",
      currency: { kind: "as_enacted", date: "1950-08-30", amended: { status: "no_record", latest: null, evidence: [] } },
    },
    "/us/stat/39/929": { exists: false },
  };

  it("links a resolved reference to this site with hover text", () => {
    const xml = `<section ${NS}><content><ref href="/us/pl/81/740/s3">section 3</ref></content></section>`;
    const out = html(xml, null, labels);
    expect(out).toContain('<a class="uslm-ref" href="/app/us/pl/81/740/s3" title="Public Law 81-740 § 3">section 3</a>');
  });

  it("links a US Code reference to the US Code site as external", () => {
    const xml = `<section ${NS}><content><ref href="/us/usc/t20/s151">20 U.S.C. 151</ref></content></section>`;
    const out = html(xml);
    expect(out).toContain('<a class="uslm-ref usa-link usa-link--external" href="https://uscode.linkedlegislation.org/us/usc/t20/s151">20 U.S.C. 151</a>');
  });

  it("links a missing Stat. page to govinfo", () => {
    const xml = `<section ${NS}><content><ref href="/us/stat/39/929">39 Stat. 929</ref></content></section>`;
    const out = html(xml, null, labels);
    expect(out).toContain('href="https://www.govinfo.gov/link/statute/39/929"');
  });

  it("renders an unlabelled reference as an href-less cite", () => {
    const xml = `<section ${NS}><content><ref href="/us/stat/60/775">60 Stat. 775</ref></content></section>`;
    const out = html(xml);
    expect(out).toContain('<cite class="uslm-ref uslm-ref--plain">60 Stat. 775</cite>');
    expect(out).not.toContain("<a ");
  });

  it("collects every ref href in document order", () => {
    const fragment = parseFragment(fixture("pl-81-740-s3.xml"));
    expect(hrefs(fragment)).toEqual(["/us/stat/39/929", "/us/stat/60/775", "/us/usc/t20/s151"]);
  });
});

describe("sidenotes and page markers", () => {
  it("renders a sidenote as an aside with role note", () => {
    const xml = `<section ${NS}><chapeau>text<sidenote><p class="fontsize8">Purposes.</p></sidenote></chapeau></section>`;
    const out = html(xml);
    expect(out).toContain('<aside class="uslm-sidenote" role="note"><p class="uslm-p fontsize8">Purposes.</p></aside>');
  });

  it("renders a page marker as a link to the govinfo page, labelled by its text", () => {
    const xml = `<section ${NS}><page identifier="/us/stat/64/564">64 <inline class="smallCaps">Stat</inline>. 564</page></section>`;
    const out = html(xml);
    expect(out).toContain('<a class="uslm-page" id="/us/stat/64/564" href="https://www.govinfo.gov/link/statute/64/564">64 Stat. 564</a>');
  });

  it("labels a page marker with no text by its identifier", () => {
    const xml = `<section ${NS}><page identifier="/us/stat/137/13"/></section>`;
    expect(html(xml)).toContain(">/us/stat/137/13</a>");
  });

  it("renders a page marker without a Stat. identifier as a span", () => {
    const xml = `<section ${NS}><page>13</page></section>`;
    expect(html(xml)).toContain('<span class="uslm-page">13</span>');
  });
});

describe("the fixtures", () => {
  it("renders section 3 of Public Law 81-740 with its paragraphs, sidenotes and page marker", () => {
    const out = html(fixture("pl-81-740-s3.xml"), "/us/pl/81/740/s3/3");
    expect(out).toContain('id="/us/pl/81/740/s3"');
    expect(out).toContain('class="uslm-paragraph prov firstIndent1 fontsize10 target" id="/us/pl/81/740/s3/3"');
    expect(out.match(/<aside class="uslm-sidenote"/gu)).toHaveLength(2);
    expect(out).toContain('href="https://www.govinfo.gov/link/statute/64/564"');
    expect(out).toContain('href="https://uscode.linkedlegislation.org/us/usc/t20/s151"');
  });

  it("renders the compiled section with its editorial note", () => {
    const out = html(fixture("sComp-83-703-tI-ch1-s1.xml"));
    expect(out).toContain('id="/us/sComp/83/703/tI/ch1./s1/a"');
    expect(out).toMatch(/<div class="uslm-editorialNote" style="[^"]*">/u);
    expect(out).toContain('href="https://uscode.linkedlegislation.org/us/usc/t42/s2011"');
  });

  it("renders the quoted paragraphs of Public Law 118-5 as a block quotation with a page marker inside", () => {
    const out = html(fixture("pl-118-5-s101-a.xml"), "/us/pl/118/5/dA/tI/s101/a");
    expect(out).toContain('class="uslm-subsection prov firstIndent0 fontsize10 target" id="/us/pl/118/5/dA/tI/s101/a"');
    expect(out).toContain('class="uslm-section target-path" id="/us/pl/118/5/dA/tI/s101"');
    expect(out).toContain('<blockquote class="uslm-quotedContent">');
    expect(out).toContain('href="https://www.govinfo.gov/link/statute/137/13"');
    expect(out).toContain('<span class="uslm-quotedText">and</span>');
  });

  it("renders the restated Atomic Energy Act inside its amending section", () => {
    const out = html(fixture("pl-83-703-s1-slice.xml"));
    expect(out).toContain('<blockquote class="uslm-quotedContent">');
    expect(out).toContain('<div class="uslm-toc">');
    expect(out).toContain('<div class="uslm-referenceItem">');
    // The quoted section is a section of the 1954 act, not of Public Law 83-703.
    expect(out).toContain('<div class="uslm-section prov');
  });

  it("renders a Statutes at Large page's slice, a mid-law page (B2)", () => {
    const root = parseFragment(fixture("statpage-64-564.xml"));
    const slices = sliceElements(root);
    expect(slices).toHaveLength(1);

    const out = render(slices[0], { target: null, labels: {} });
    // The slice is a plain container: `slice`, `pLaw` and `main` are not in
    // the element map, so each falls to the default div wrap.
    expect(out).toContain('<div class="uslm-slice">');
    expect(out).toContain('<div class="uslm-pLaw">');
    expect(out).toContain('<div class="uslm-main">');
    // Section 3 continues from the previous page; section 4 starts here.
    expect(out).toContain('<div class="uslm-section firstIndent1 fontsize10" id="/us/pl/81/740/s3">');
    expect(out).toContain('<div class="uslm-section firstIndent1 fontsize10" id="/us/pl/81/740/s4">');
    // The page's own opening marker links to this page; the page's closing
    // marker, inherited from the next one, links to the next.
    expect(out).toContain('<a class="uslm-page" id="/us/stat/64/564" href="https://www.govinfo.gov/link/statute/64/564">64 Stat. 564</a>');
    expect(out).toContain('href="https://www.govinfo.gov/link/statute/64/565">64 Stat. 565</a>');
    expect(out).toContain('<aside class="uslm-sidenote" role="note">');
  });
});

describe("titleClass", () => {
  it("is smallCaps when the root's own heading carries it", () => {
    const xml = `<section ${NS}><heading class="smallCaps centered">instructions</heading><num value="804">Sec. 804.</num></section>`;
    expect(titleClass(parseFragment(xml))).toBe("smallCaps");
  });

  it("is null for a plain heading, and ignores headings below the root", () => {
    expect(titleClass(parseFragment(`<section ${NS}><heading>Short title</heading></section>`))).toBeNull();
    const nested = `<section ${NS}><content><quotedContent><section><heading class="smallCaps">x</heading></section></quotedContent></content></section>`;
    expect(titleClass(parseFragment(nested))).toBeNull();
  });
});
