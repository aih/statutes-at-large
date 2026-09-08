"""Law-number collisions inside a volume (ingest/numbering.py)."""

from ingest.numbering import Claim, plan_numbering


def claim(seq, number, kind="pl", chapter=True):
    return Claim(
        seq=seq, kind=kind, number=number, primary=f"/us/{kind}/81/{number}",
        chapter_form=f"/us/act/1950-01-01/ch{seq}" if chapter else None,
        citation=f"64 Stat. {seq}", title=None,
    )


def test_the_claimant_out_of_sequence_is_demoted_to_its_chapter():
    plan = plan_numbering([claim(1, 440), claim(2, 835), claim(3, 442), claim(9, 835), claim(10, 836)])
    assert set(plan.decisions) == {2}
    decision = plan.decisions[2]
    assert decision.action == "demote" and decision.kept_as == "/us/act/1950-01-01/ch2"
    assert plan.out_of_sequence == []


def test_without_a_chapter_form_the_loser_is_dropped():
    plan = plan_numbering([claim(1, 411, chapter=False), claim(2, 412, chapter=False), claim(5, 412, chapter=False), claim(6, 415, chapter=False)])
    assert plan.decisions[5].action == "drop"
    assert plan.decisions[5].kept_as is None


def test_the_first_claimant_wins_when_neither_fits():
    plan = plan_numbering([claim(1, 500), claim(2, 900), claim(3, 900), claim(4, 501)])
    assert set(plan.decisions) == {3}


def test_series_are_independent_and_out_of_sequence_numbers_are_reported():
    plan = plan_numbering([claim(1, 10), claim(2, 10, kind="pvtl"), claim(3, 12), claim(4, 5)])
    assert plan.decisions == {}
    assert 4 in {row["seq"] for row in plan.out_of_sequence}
