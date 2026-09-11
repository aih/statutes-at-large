"""`source_sentence`: the note's last sentence, per source and identifier provenance."""

from types import SimpleNamespace

from params import source_sentence


def law(collection: str, package: str, volume: int, identifiers: str) -> SimpleNamespace:
    return SimpleNamespace(
        source_collection=collection, source_package=package, stat_volume=volume, provenance_identifiers=identifiers
    )


def test_a_digitized_volume():
    assert source_sentence(law("STATUTE", "STATUTE-97", 97, "rules-1.0")) == (
        "The text is from GovInfo package STATUTE-97, converted to USLM from the scanned volume by "
        "GPO's digitization vendor; the identifiers below the law are assigned here by rule (rules-1.0)."
    )


def test_a_typeset_volume():
    assert source_sentence(law("STATUTE", "STATUTE-117", 117, "rules-1.0")) == (
        "The text is from GovInfo package STATUTE-117, converted to USLM by GPO from its typesetting "
        "(locator) files; the identifiers below the law are assigned here by rule (rules-1.0)."
    )


def test_a_plaw_file_with_identifiers_filled_in():
    assert source_sentence(law("PLAW", "PLAW-118publ1", 137, "gpo-uslm+rules-1.0")) == (
        "The text is from GovInfo package PLAW-118publ1, converted to USLM by GPO from its typesetting "
        "(locator) files; the identifiers are GPO's, and those GPO left out are assigned here by rule (rules-1.0)."
    )
