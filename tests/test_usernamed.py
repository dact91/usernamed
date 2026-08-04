import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import usernamed as u  # noqa: E402


def test_parse_name_basic():
    assert u.parse_name("Mitch Ressek") == ("mitch", "", "ressek")


def test_parse_name_with_middle():
    assert u.parse_name("Mitch Alan Ressek") == ("mitch", "alan", "ressek")


def test_parse_name_last_comma_first():
    assert u.parse_name("Ressek, Mitch") == ("mitch", "", "ressek")


def test_parse_name_single_word_returns_none():
    assert u.parse_name("Cher") is None


def test_parse_name_accents_are_folded():
    first, middle, last = u.parse_name("Björn Rådzík")
    assert first == "bjorn"
    assert last == "radzik"


def test_format_first_l_exists_and_is_correct():
    # This is the format username-anarchy is missing.
    fn, _desc = u.FORMATS["first.l"]
    assert fn("mitch", "", "ressek") == "mitch.r"


def test_format_f_last():
    fn, _desc = u.FORMATS["f.last"]
    assert fn("mitch", "", "ressek") == "m.ressek"


def test_middle_aware_formats_return_none_without_middle():
    fn, _desc = u.FORMATS["first.m.last"]
    assert fn("mitch", "", "ressek") is None


def test_middle_aware_formats_work_with_middle():
    fn, _desc = u.FORMATS["first.m.last"]
    assert fn("mitch", "alan", "ressek") == "mitch.alan.ressek"


def test_generate_dedupes_by_default():
    names = [("mitch", "", "ressek")]
    results = list(u.generate(iter(names), ["first.last", "first.last"], None, "lower", True, False, False))
    assert results == ["mitch.ressek"]


def test_generate_domain_suffix():
    names = [("mitch", "", "ressek")]
    results = list(u.generate(iter(names), ["first.last"], "corp.local", "lower", True, False, False))
    assert results == ["mitch.ressek@corp.local"]


def test_generate_numeric_suffix():
    names = [("mitch", "", "ressek")]
    results = list(u.generate(iter(names), ["first.last"], None, "lower", True, True, False))
    assert results == ["mitch.ressek", "mitch.ressek1"]


def test_generate_nicknames_expand_first_name():
    names = [("daniel", "", "ramus")]
    results = list(u.generate(iter(names), ["first.last"], None, "lower", True, False, True))
    assert "daniel.ramus" in results
    assert "dan.ramus" in results
    assert "danny.ramus" in results


def test_apply_case_upper():
    assert u.apply_case("mitch.ressek", "upper") == "MITCH.RESSEK"


def test_apply_case_asis_preserves_input():
    assert u.apply_case("MRessek", "asis") == "MRessek"


def test_all_formats_are_callable():
    for name, (fn, desc) in u.FORMATS.items():
        result = fn("mitch", "alan", "ressek")
        assert result is None or isinstance(result, str), f"format {name} returned unexpected type"
