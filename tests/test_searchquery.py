"""What a query string means, and what it becomes.

`storage/searchquery.py` is pure, so this runs with no database and no cluster.
The route's contract is `tests/test_search_route.py`; this is the module
underneath it.
"""

import pytest

from storage.searchquery import (
    DEFAULT_VIEW,
    FACETS,
    KINDS,
    QUERY_SYNTAX_FLAGS,
    SCOPE_FIELDS,
    SORTS,
    VIEWS,
    build_search_body,
    effective_view,
    law_identifier_of,
    parse_query,
    unparse_query,
    with_filter,
    without_filter,
)


def filters_of(body) -> list:
    return body["query"]["bool"]["filter"]


def must_of(body) -> list:
    return body["query"]["bool"].get("must", [])


class TestParsing:
    def test_a_plain_query_is_all_text(self):
        parsed = parse_query("wild horses")
        assert parsed.text == "wild horses"
        assert parsed.filters == {}

    def test_a_scope_is_lifted_out_of_the_text(self):
        parsed = parse_query("appropriations congress:117")
        assert parsed.text == "appropriations"
        assert parsed.filters == {"congress": ("117",)}

    def test_a_law_number_becomes_an_identifier(self):
        assert parse_query("law:117-328").filters == {"law_identifier": ("/us/pl/117/328",)}

    def test_an_identifier_is_taken_as_written(self):
        """`law:` filters the whole identifier, so a private law and an act are
        named the same way a public law is."""
        for value in ("/us/pvtl/81/375", "/us/act/1890-07-02/ch647"):
            assert parse_query(f"law:{value}").filters == {"law_identifier": (value,)}
        assert law_identifier_of("117-328") == "/us/pl/117/328"

    def test_the_remaining_scopes(self):
        parsed = parse_query("x year:1996 vol:110 kind:pvtl")
        assert parsed.filters == {"year": ("1996",), "volume": ("110",), "kind": ("pvtl",)}

    def test_a_quoted_value_survives_its_prefix(self):
        parsed = parse_query('heading:"wild horses"')
        assert parsed.heading_terms == ("wild horses",)
        assert parsed.text == ""

    def test_a_bare_phrase_is_still_a_phrase(self):
        parsed = parse_query('"national forest" vol:110')
        assert parsed.text == '"national forest"'
        assert parsed.filters == {"volume": ("110",)}

    def test_an_unknown_prefix_stays_in_the_text(self):
        assert parse_query("see: also").text == "see: also"

    def test_a_scope_with_no_value_stays_in_the_text(self):
        assert parse_query("water congress:").text == "water congress:"

    def test_a_scope_value_it_cannot_mean_stays_in_the_text(self):
        # A filter on a value no document holds is an empty result set that
        # reads like a search; leaving it in the text is a search.
        assert parse_query("congress:soon").text == "congress:soon"
        assert parse_query("kind:statute").text == "kind:statute"
        assert parse_query("view:enacte").text == "view:enacte"

    def test_repeated_values_of_one_field_are_kept(self):
        assert parse_query("x congress:117 congress:118").filters == {
            "congress": ("117", "118")
        }

    def test_the_view_is_read_but_not_a_filter(self):
        parsed = parse_query("wild horses view:compiled")
        assert parsed.view == "compiled"
        assert parsed.filters == {}

    def test_a_query_of_only_scopes_is_not_empty(self):
        assert not parse_query("congress:117").is_empty()

    def test_a_view_alone_is_empty(self):
        assert parse_query("view:compiled").is_empty()

    def test_a_query_of_nothing_is_empty(self):
        assert parse_query("   ").is_empty()

    def test_every_scope_field_is_reachable_from_a_query(self):
        """Guards the parse table: a name added to `SCOPE_FIELDS` and to no
        branch of `parse_query` would be searched as text."""
        values = {"law": "117-328", "congress": "117", "year": "1996",
                  "vol": "110", "kind": "pl", "heading": "water"}
        for name in SCOPE_FIELDS:
            assert parse_query(f"{name}:{values[name]}").text == "", name


class TestRoundTrip:
    @pytest.mark.parametrize(
        "query",
        [
            "wild horses congress:117",
            'heading:"wild horses"',
            "appropriations kind:pl view:compiled",
            "water vol:110 vol:124",
            "law:/us/act/1890-07-02/ch647",
        ],
    )
    def test_unparse_reproduces_a_query_that_parses_the_same(self, query):
        assert parse_query(unparse_query(parse_query(query))) == parse_query(query)

    def test_a_law_number_round_trips_as_its_identifier(self):
        assert unparse_query(parse_query("law:117-328")) == "law:/us/pl/117/328"

    def test_adding_a_filter_is_idempotent(self):
        once = with_filter(parse_query("water"), "congress", "117")
        assert with_filter(once, "congress", "117") == once

    def test_a_facet_link_sets_the_view(self):
        parsed = with_filter(parse_query("water"), "view", "compiled")
        assert parsed.view == "compiled"
        assert without_filter(parsed, "view", "compiled").view is None

    def test_removing_the_last_value_removes_the_field(self):
        parsed = with_filter(parse_query("water"), "kind", "pl")
        assert without_filter(parsed, "kind", "pl").filters == {}

    def test_a_value_the_scope_cannot_mean_is_ignored(self):
        parsed = parse_query("water")
        assert with_filter(parsed, "congress", "soon") == parsed


class TestBody:
    def test_the_text_is_matched_as_typed(self):
        clause = must_of(build_search_body(parse_query("wild horses")))[0][
            "simple_query_string"
        ]
        assert clause["default_operator"] == "and"
        assert clause["flags"] == QUERY_SYNTAX_FLAGS
        assert clause["fields"] == ["heading^2", "text"]
        assert "fuzziness" not in clause

    def test_the_whole_body_asks_for_no_fuzziness(self):
        # An edit distance on every term matched `company` for `compare`, and a
        # fuzzy hit scores as a full match (the US Code site's ADR-0031).
        assert "fuzziness" not in str(build_search_body(parse_query("compare")))

    def test_a_scope_becomes_a_filter_not_a_search_term(self):
        body = build_search_body(parse_query("appropriations congress:117"))
        assert {"terms": {"congress": [117]}} in filters_of(body)
        assert "congress" not in str(must_of(body))

    def test_a_numeric_field_is_filtered_by_integers(self):
        body = build_search_body(parse_query("x year:1996 vol:110"))
        assert {"terms": {"year": [1996]}} in filters_of(body)
        assert {"terms": {"volume": [110]}} in filters_of(body)

    def test_a_heading_scope_becomes_its_own_clause(self):
        clause = must_of(build_search_body(parse_query("heading:wilderness")))[0][
            "simple_query_string"
        ]
        assert clause["fields"] == ["heading"]
        assert clause["query"] == "wilderness"

    def test_the_default_view_is_enacted(self):
        assert DEFAULT_VIEW == "enacted"
        body = build_search_body(parse_query("wild horses"))
        assert {"term": {"view": "enacted"}} in filters_of(body)

    def test_compiled_filters_the_other_way(self):
        body = build_search_body(parse_query("wild horses"), view="compiled")
        assert {"term": {"view": "compiled"}} in filters_of(body)

    def test_all_collapses_nothing(self):
        # An enacted and a compiled section are two answers.
        body = build_search_body(parse_query("wild horses"), view="all")
        assert not [f for f in filters_of(body) if "view" in str(f)]
        assert "collapse" not in body

    @pytest.mark.parametrize(
        "parsed_view,requested,expected",
        [(None, None, "enacted"), (None, "compiled", "compiled"),
         ("all", "compiled", "all"), (None, "nonsense", "enacted")],
    )
    def test_the_query_wins_over_the_parameter(self, parsed_view, requested, expected):
        parsed = parse_query(f"x view:{parsed_view}" if parsed_view else "x")
        assert effective_view(parsed, requested) == expected

    def test_the_phrase_boost_is_a_should_not_a_must(self):
        # It reorders results; it must never remove one.
        body = build_search_body(parse_query("wild horses"))
        assert any("match_phrase" in c for c in body["query"]["bool"]["should"])
        assert not any("match_phrase" in c for c in must_of(body))

    def test_no_phrase_clause_for_a_single_word(self):
        assert not build_search_body(parse_query("wilderness"))["query"]["bool"].get("should")

    def test_no_phrase_clause_when_the_query_carries_operators(self):
        """`match_phrase` has no operator syntax, so boosting `park | forest`
        as a phrase would score the literal word `|`."""
        assert not build_search_body(parse_query("park | forest"))["query"]["bool"].get(
            "should"
        )

    def test_the_highlighter_marks_the_text_with_em(self):
        highlight = build_search_body(parse_query("wild horses"))["highlight"]
        assert highlight["pre_tags"] == ["<em>"] and highlight["post_tags"] == ["</em>"]
        assert "text" in highlight["fields"]

    @pytest.mark.parametrize(
        "sort,field,order", [("date", "enacted", "desc"), ("citation", "citation_sort", "asc")]
    )
    def test_an_explicit_sort_replaces_the_score(self, sort, field, order):
        body = build_search_body(parse_query("wild horses"), sort=sort)
        assert body["sort"][0][field] == {"order": order, "missing": "_last"}
        assert body["sort"][1] == "_score"

    def test_relevance_sends_no_sort_at_all(self):
        assert "sort" not in build_search_body(parse_query("wild horses"))
        assert SORTS[0] == "relevance"

    def test_the_pager_is_the_body_window(self):
        body = build_search_body(parse_query("x"), limit=20, offset=40)
        assert (body["from"], body["size"]) == (40, 20)

    def test_the_total_is_not_capped(self):
        # OpenSearch stops counting at 10,000 unless told otherwise and reports
        # the cap as the answer.
        assert build_search_body(parse_query("x"))["track_total_hits"] is True

    def test_facets_count_the_three_fields(self):
        body = build_search_body(parse_query("wild horses"), facets=True)
        assert set(body["aggs"]) == set(FACETS)
        assert body["aggs"]["kind"]["terms"]["size"] == len(KINDS)

    def test_no_facets_by_default(self):
        assert "aggs" not in build_search_body(parse_query("wild horses"))

    def test_the_views_are_the_three_the_route_accepts(self):
        assert VIEWS == ("enacted", "compiled", "all")
