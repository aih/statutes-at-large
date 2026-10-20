"""The Repository over the loaded slices: the four resolution rules, provision
cutting, pages, labels, status."""

import datetime


def test_exact_section(repo):
    result = repo.get_unit("/us/pl/81/740/s3")
    assert result.resolution == "exact" and result.level == "section" and result.num == "3"
    assert result.served_identifier == "/us/pl/81/740/s3"
    assert result.law.label == "Public Law 81-740" and result.law.citation == "64 Stat. 563"
    assert [p.identifier for p in result.pages] == ["/us/stat/64/563", "/us/stat/64/564"]
    assert result.pages[0].pdf == "https://www.govinfo.gov/link/statute/64/563"
    assert result.text.startswith("Sec. 3. The objects and purposes")
    assert result.content_hash and len(result.content_hash) == 64


def test_a_provision_below_the_section_is_cut_from_it(repo):
    result = repo.get_unit("/us/pl/81/740/s3/1")
    assert result.resolution == "exact"
    assert result.served_identifier == "/us/pl/81/740/s3"
    assert result.provision.found and result.provision.identifier == "/us/pl/81/740/s3/1"
    assert result.provision.text.startswith("(1) to create, foster, and assist")
    assert result.provision.xml.startswith("<paragraph")


def test_a_missing_provision_is_a_prefix_answer(repo):
    result = repo.get_unit("/us/pl/81/740/s3/9")
    assert result.resolution == "prefix"
    assert result.served_identifier == "/us/pl/81/740/s3"
    assert result.provision.found is False


def test_rule_4_the_chapter_form_of_a_numbered_law(repo):
    result = repo.get_unit("/us/act/1950-08-30/ch823/s3")
    assert result.resolution == "alias"
    assert result.served_identifier == "/us/pl/81/740/s3"
    assert result.law.aliases == ("/us/pl/81/740", "/us/act/1950-08-30/ch823")


def test_rule_3_section_number_under_another_hierarchy(repo):
    result = repo.get_unit("/us/pl/81/910/s101")
    assert result.resolution == "section_number"
    assert result.served_identifier == "/us/pl/81/910/tI/s101"
    assert result.ancestors[0].identifier == "/us/pl/81/910/tI"
    by_number = repo.get_section_by_number("/us/pl/81/910", "101")
    assert by_number.served_identifier == "/us/pl/81/910/tI/s101"
    assert repo.get_section_by_number("/us/pl/81/910", "999") is None


def test_rule_2_the_law_is_the_longest_prefix(repo):
    result = repo.get_unit("/us/pl/81/740/s99")
    assert result.resolution == "prefix" and result.level == "law"
    assert result.served_identifier == "/us/pl/81/740"
    assert len(result.children) == 21


def test_the_law_itself(repo):
    result = repo.get_unit("/us/pl/81/910")
    assert result.level == "law" and result.resolution == "exact"
    assert [c.identifier for c in result.children][:2] == ["/us/pl/81/910/tI", "/us/pl/81/910/tI–A"]
    assert result.law.enacted == datetime.date(1951, 1, 6)
    summary = repo.get_law("/us/act/1951-01-06/ch1212")
    assert summary.section_count == 11 and summary.toc[0].level == "title"


def test_a_laws_text_and_xml_are_empty_for_every_format(repo):
    """ADR-0019: a law's `text` is never computed and `Law.xml` is not read,
    for `wanted="xml"` as for JSON."""
    for wanted in ("json", "xml"):
        result = repo.get_unit("/us/pl/81/910", wanted=wanted)
        assert result.text == "" and result.xml == ""


def test_a_hierarchy_node(repo):
    result = repo.get_unit("/us/pl/111/344/tI")
    assert result.level == "title" and result.heading.startswith("EXTENSION OF TRADE")
    assert result.children and all(c.identifier.startswith("/us/pl/111/344/tI/") for c in result.children)


def test_a_hierarchy_nodes_text_and_xml_are_empty_for_every_format(repo):
    for wanted in ("json", "xml"):
        result = repo.get_unit("/us/pl/111/344/tI", wanted=wanted)
        assert result.text == "" and result.xml == ""


def test_nothing_loaded(repo):
    assert repo.get_unit("/us/pl/81/999999") is None
    assert repo.get_unit("/us/usc/t16/s1") is None
    assert repo.get_unit("/us/sComp/83/703/s1") is None
    assert repo.get_law("/us/act/1900-01-01/ch1") is None


def test_stat_pages(repo):
    page = repo.stat_page(64, "564")
    assert page.identifier == "/us/stat/64/564"
    assert page.pdf == "https://www.govinfo.gov/link/statute/64/564"
    assert [(d.law.identifier, d.starts_here, d.unit_identifier) for d in page.documents] == [("/us/pl/81/740", False, "/us/pl/81/740/s3")]
    first = repo.stat_page(64, "3")
    assert [(d.law.identifier, d.starts_here) for d in first.documents] == [("/us/pl/81/441", True), ("/us/pl/81/442", True)]
    assert repo.stat_page(64, "a12").documents[0].law.identifier == "/us/pvtl/81/375"
    assert repo.stat_page(64, "99999") is None


def test_a_stat_page_slice(repo):
    """Public Law 81-740 starts on 64 Stat. 563: the slice begins with the
    preface and ends at the marker for 564."""
    first = repo.stat_page(64, "563", with_slices=True).documents[0]
    assert first.to_identifier == "/us/stat/64/564"
    assert first.text.startswith("[CHAPTER 823] AN ACT To incorporate the Future Farmers of America")
    assert [u.identifier for u in first.units] == [
        "/us/pl/81/740/s1",
        "/us/pl/81/740/s2",
        "/us/pl/81/740/s3",
    ]
    later = repo.stat_page(64, "564", with_slices=True).documents[0]
    assert later.to_identifier == "/us/stat/64/565"
    assert later.text.startswith("(3) to create and nurture a love of country life")
    assert "Future Farmers of America, and for other purposes" not in later.text
    assert [u.identifier for u in later.units] == ["/us/pl/81/740/s3", "/us/pl/81/740/s4"]
    assert later.units[0].level == "section" and later.units[0].num == "3"


def test_a_stat_page_carries_no_slice_unless_it_is_asked_for(repo):
    document = repo.stat_page(64, "564").documents[0]
    assert document.xml is None and document.text is None and document.units == ()


def test_each_law_on_a_page_has_its_own_slice(repo):
    """Chapters 1 and 2 both start on 64 Stat. 3; neither slice holds the
    other's text."""
    documents = repo.stat_page(64, "3", with_slices=True).documents
    assert [d.law.identifier for d in documents] == ["/us/pl/81/441", "/us/pl/81/442"]
    assert "National Children’s Dental Health Day" in documents[0].text
    assert "National Children’s Dental Health Day" not in documents[1].text
    assert "Federal Firearms Act" in documents[1].text


def test_a_marker_inside_quoted_content_names_a_page(repo):
    """124 Stat. 3613 begins inside a quoted section (gotcha 5): the slice
    starts at that marker and the unit is the section that holds the quote."""
    document = repo.stat_page(124, "3613", with_slices=True).documents[0]
    assert document.unit_identifier == "/us/pl/111/344/tI/stA/s101"
    assert [u.identifier for u in document.units] == ["/us/pl/111/344/tI/stA/s101"]
    assert document.to_identifier == "/us/stat/124/3614"


def test_labels(repo):
    found = repo.labels(["/us/pl/81/740/s3", "/us/act/1950-08-30/ch823", "/us/pl/81/1", "/us/pl/118/34/s1"])
    assert set(found) == {"/us/pl/81/740/s3", "/us/act/1950-08-30/ch823", "/us/pl/118/34/s1"}
    assert found["/us/act/1950-08-30/ch823"].served_identifier == "/us/pl/81/740"
    assert found["/us/pl/118/34/s1"].heading == "SHORT TITLE; TABLE OF CONTENTS."
    assert found["/us/pl/81/740/s3"].law.kind == "pl"


def test_labels_batch_resolution(repo):
    batch = [
        "/us/pl/81/740/s3",
        "/us/pl/81/740/s3",  # duplicate
        "/us/act/1950-08-30/ch823",
        "/us/pl/111/344/tI",
        "/us/pl/111/344/tI/stA/s101",
        "/us/pl/81/9999",  # nonexistent law
        "/us/pl/81/740/s9999",  # nonexistent section in known law -> prefix resolution
    ]
    found = repo.labels(batch)
    assert set(found) == {
        "/us/pl/81/740/s3",
        "/us/act/1950-08-30/ch823",
        "/us/pl/111/344/tI",
        "/us/pl/111/344/tI/stA/s101",
        "/us/pl/81/740/s9999",
    }
    assert found["/us/pl/81/740/s3"].resolution == "exact"
    assert found["/us/act/1950-08-30/ch823"].resolution == "alias"
    assert found["/us/pl/111/344/tI"].level == "title"
    assert found["/us/pl/111/344/tI/stA/s101"].level == "section"
    assert found["/us/pl/81/740/s9999"].resolution == "prefix"
    assert found["/us/pl/81/740/s9999"].served_identifier == "/us/pl/81/740"



def test_status(repo):
    status = repo.collection_status("STATUTE")
    assert status.volumes == (26, 64, 68, 72, 116, 124, 137)
    assert status.laws == 26 and status.latest_package == "STATUTE-137"
    check = repo.last_source_check("STATUTE")
    assert check.ok and check.newest_package == "STATUTE-137" and not check.is_stale()
    plaw = repo.collection_status("PLAW")
    assert plaw.laws == 4 and plaw.laws_by_congress == ((118, 3), (119, 1)) and plaw.congresses == (118, 119)
    assert plaw.latest_package == "PLAW-119publ1" and plaw.volumes == (137, 139)
    assert repo.last_source_check("PLAW").newest_package == "PLAW-119publ1"


def test_act_matches_atomic_energy_act(repo):
    """Public Law 83-703's short title is inside `quotedContent`, so the law
    has none of its own; the compilation names it, and 42 U.S.C. 2011's Short
    Title note cites the 1954 act as adding the short title section."""
    matches = repo.act_matches('"Atomic energy act of 1954"')
    assert [m.title for m in matches] == ["Atomic Energy Act of 1954"]
    match = matches[0]
    assert match.compilation.identifier_prefix == "/us/sComp/83/703"
    assert match.compilation.package_id == "COMPS-1630"
    assert match.compilation.current.current_through_pl == "118-67"

    assert match.law.identifier == "/us/pl/83/703"
    assert match.law.label == "Public Law 83-703"
    assert "/us/act/1954-08-30/ch1073" in match.law.aliases
    assert match.law.citation == "68 Stat. 919"
    assert match.law.enacted == datetime.date(1954, 8, 30)

    usc = match.canonical_usc
    assert usc.identifier == "/us/usc/t42/s2011"
    assert usc.citation == "42 U.S.C. § 2011"
    assert usc.heading == "Congressional declaration of policy"
    assert (usc.context, usc.note_topic) == ("note", "shortTitle")
    assert usc.citing_sections_count >= 8
    assert [h.label for h in usc.history] == [
        "Act of August 1, 1946, ch. 724, title I, § 291",
        "Act of August 30, 1954, ch. 1073, § 1",
        "68 Stat. 960",
        "Public Law 102-486, title IX, § 902(a)(8)",
        "106 Stat. 2944",
    ]
    assert repo.act_matches("atomic energy")[0].title == "Atomic Energy Act of 1954"


def test_act_matches_sherman_act_falls_back_to_the_enacting_source_credit(repo):
    """15 U.S.C. 1's Short Title note cites only the 1976 law that added the
    short title, so the section is found by its source credit, which cites
    the Sherman Act before its first Stat. page."""
    match = repo.act_matches("Sherman Act")[0]
    assert match.title == "Sherman Act"
    assert match.compilation.identifier_prefix == "/us/sComp/51/647"
    assert match.compilation.package_id == "COMPS-3055"
    assert match.law.identifier == "/us/act/1890-07-02/ch647"
    usc = match.canonical_usc
    assert usc.identifier == "/us/usc/t15/s1"
    assert (usc.context, usc.note_topic) == ("sourceCredit", None)
    assert [h.label for h in usc.history[:2]] == ["Act of July 2, 1890, ch. 647, § 1", "26 Stat. 209"]


def test_an_amending_law_is_not_given_the_section_it_amended(repo):
    """Public Law 111-344 is cited in 19 U.S.C. 2296's source credit after
    the Trade Act of 1974 and its Stat. page: it amended that section."""
    match = repo.act_matches("Omnibus Trade Act of 2010")[0]
    assert match.compilation is None and match.law.identifier == "/us/pl/111/344"
    assert match.canonical_usc is None


def test_act_matches_whole_words_only(repo):
    assert repo.act_matches("act") == []
    assert repo.act_matches("of") == []
    assert repo.act_matches("a") == []
    assert repo.act_matches("1954") == []
    assert repo.act_matches("the act of 2010") == []
    assert repo.act_matches("nuclear") == []
    assert repo.act_matches("energ") == []
    assert [m.title for m in repo.act_matches("security")] == ["Federal Food, Drug, and Cosmetic Act", "Social Security Act"]


def test_one_title_file_of_an_act_is_one_act_and_list_comps_keeps_every_file(repo, db):
    """`act_matches` answers one card per prefix, titled with the act's name;
    `list_comps` lists files, so both title files of the Social Security Act
    stay in it."""
    from db.models import Comp

    title_ii = db.query(Comp).filter_by(file_id="8755").one()
    db.add(
        Comp(
            file_id="99999",
            package_id="COMPS-99999",
            identifier_prefix=title_ii.identifier_prefix,
            law_congress=title_ii.law_congress,
            law_number=title_ii.law_number,
            title=title_ii.title,
            display_title="Social Security Act-TITLE XVIII (Health Insurance for the Aged and Disabled)",
            short_titles=list(title_ii.short_titles),
            partial_of="XVIII",
        )
    )
    db.flush()
    try:
        matches = repo.act_matches("medicare")
        assert [(m.title, m.compilation.identifier_prefix) for m in matches] == [("Social Security Act", "/us/sComp/74/271")]
        assert sorted(c.file_id for c in repo.list_comps(q="medicare")) == ["8755", "99999"]
    finally:
        db.rollback()


def test_list_comps_puts_a_whole_title_first(repo, db):
    from db.models import Comp

    db.add(Comp(file_id="99998", package_id="COMPS-99998", identifier_prefix="/us/sComp/99/1",
                display_title="Antitrust Amendments to the Sherman Act", short_titles=[]))
    db.flush()
    try:
        assert [c.file_id for c in repo.list_comps(q='"sherman act"')] == ["3055", "99998"]
    finally:
        db.rollback()
