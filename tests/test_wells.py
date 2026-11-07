import pytest

from submission.archive_qa.wells import canonical_well, find_wells, known_wells, well_code
from tests.conftest import needs_data


@pytest.mark.parametrize("text, expected", [
    ("NO 15/9-F-1 C", "15/9-F-1-C"),
    ("15/9-F-1 C", "15/9-F-1-C"),
    ("15_9_F_1_C", "15/9-F-1-C"),
    ("15/9-F-1-C", "15/9-F-1-C"),
    ("15/9-F-11 B", "15/9-F-11-B"),
    ("15/9-F-11-B", "15/9-F-11-B"),
    ("F-11-B", "15/9-F-11-B"),
    ("15/9-F-11-T2", "15/9-F-11-T2"),
    ("F-11-T2", "15/9-F-11-T2"),
    ("15_9_F_11_T2", "15/9-F-11-T2"),
    ("15/9-19-A", "15/9-19-A"),
    ("NO 15/9-19 A", "15/9-19-A"),
    ("15_9_19_A", "15/9-19-A"),
    ("15/9-F-14", "15/9-F-14"),
    ("F-12", "15/9-F-12"),
    ("15/9-F-15-D", "15/9-F-15-D"),
    ("underscores_and_no: NO 15/9-F-12", "15/9-F-12"),
])
def test_canonical_variants(text, expected):
    assert canonical_well(text) == expected


def test_no_well_returns_none():
    assert canonical_well("What was the density of the brine?") is None


def test_bare_f1_is_main_wellbore_only():
    assert canonical_well("F-1") == "15/9-F-1"
    assert canonical_well("15/9-F-1") == "15/9-F-1"


@pytest.mark.parametrize("longer", ["F-11", "F-12", "F-15", "F-1-B", "F-1 B", "F-11-B"])
def test_f1_never_matches_longer_names(longer):
    assert canonical_well(longer) != canonical_well("F-1")
    # and F-1 inside a sentence next to the longer name stays distinct
    wells = [m.well for m in find_wells(f"Compare F-1 and {longer} please")]
    assert wells[0] == "15/9-F-1" and wells[1] != "15/9-F-1"


def test_suffix_letters_are_case_sensitive():
    # "F-1 and ..." / "F-12 on ..." must not read the next word as a suffix
    assert [m.well for m in find_wells("on F-1 and F-12 on that day")] == ["15/9-F-1", "15/9-F-12"]


def test_find_wells_in_a_list():
    text = "Across the F-11-T2, F-1, F-1-B and F-15-D sidetracks"
    assert [m.well for m in find_wells(text)] == [
        "15/9-F-11-T2", "15/9-F-1", "15/9-F-1-B", "15/9-F-15-D"]


def test_well_code():
    assert well_code("15/9-F-1-C") == "F1C"
    assert well_code("15/9-19-A") == "19A"
    assert well_code("15/9-F-11-T2") == "F11T2"


@needs_data
def test_known_wells_come_from_files(reports):
    wells = known_wells(reports)
    assert len(reports) == 32
    assert "15/9-F-1" in wells and "15/9-F-1-C" in wells and "15/9-19-A" in wells
    assert "15/9-F-14" not in wells  # named in a question, absent from the archive
