"""Tests for lookup and calculate. No API key and no network needed."""

import time

import pytest

import tools


# ------------------------------------------------------------------ lookup

def test_lookup_finds_correct_2025_number():
    r = tools.lookup("Ossbridge", "population_2025")
    assert r["value"] == 52904
    assert r["source"] == "NR-01"


def test_lookup_misspelled_name_suggests_the_right_one():
    r = tools.lookup("Ossbrige", "population_2025")
    assert "error" in r
    assert "Ossbridge" in r["error"]
    assert "value" not in r  # never guesses silently


def test_lookup_similar_names_are_not_mixed_up():
    a = tools.lookup("Ossbridge", "population_2025")
    b = tools.lookup("Ossford", "population_2025")
    assert (a["value"], a["source"]) == (52904, "NR-01")
    assert (b["value"], b["source"]) == (30982, "NR-02")
    assert tools.lookup("ossford", "schools")["value"] == 14  # case does not matter


def test_lookup_never_uses_archived_profiles():
    r = tools.lookup("Tarnvale", "population_2019")
    assert "error" in r and "archived" in r["error"]
    current = tools.lookup("Tarnvale", "population_2025")
    assert current["value"] == 71388          # NR-03, not the 2019 estimate 65,030 from NR-13
    assert current["source"] == "NR-03"


def test_lookup_applies_correction_notice():
    r = tools.lookup("Brightwater", "area_km2")
    assert r["value"] == 921.4                # NR-16, not the typo 912.4 in NR-05
    assert "NR-16" in r["source"]


def test_lookup_converts_lindenmoor_water_to_megalitres():
    r = tools.lookup("Lindenmoor", "water_use_2025_ml")
    assert r["value"] == pytest.approx(2151.4)
    assert r["unit"] == "ML"
    assert "converted" in r["source"]
    assert tools.lookup("Kelmarsh", "water_use_2025_ml")["value"] == 1739  # megalitres already


def test_lookup_tariff_is_the_2025_one():
    r = tools.lookup("region", "water_tariff_2025")
    assert r["value"] == 142.35
    assert r["source"] == "NR-15"


@pytest.mark.parametrize("district, field", [
    (None, "schools"),
    ("Redfen", None),
    (123, 456),
    ("", ""),
    ("Redfen", "population_2025; DROP TABLE"),
    ("../../etc/passwd", "schools"),
    ("Redfen" * 1000, "schools"),
    ("region", "area_km2"),
], ids=["district-none", "field-none", "numbers", "empty", "sql-like", "path-like", "very-long-name", "region-wrong-field"])
def test_lookup_never_crashes_on_strange_input(district, field):
    r = tools.lookup(district, field)
    assert isinstance(r, dict)
    assert "error" in r


# --------------------------------------------------------------- calculate

def test_calculate_multiplication():
    assert tools.calculate("48317 * 1.0947")["result"] == pytest.approx(52892.6199)


def test_calculate_division():
    assert tools.calculate("44675 / 921.4")["result"] == pytest.approx(48.48599956587801)


def test_calculate_precedence_and_parentheses():
    assert tools.calculate("2 + 3 * 4")["result"] == 14
    assert tools.calculate("(2 + 3) * 4")["result"] == 20
    assert tools.calculate("-3 + 2")["result"] == -1
    assert tools.calculate("2 ** 10")["result"] == 1024


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo hi')",
    "(1).__class__",
    "9**9**9",
])
def test_calculate_refuses_dangerous_input(expression):
    start = time.time()
    r = tools.calculate(expression)
    assert "error" in r
    assert "result" not in r
    assert time.time() - start < 1.0          # refused quickly, did not freeze


def test_calculate_division_by_zero():
    assert tools.calculate("1 / 0") == {"error": "division by zero"}
    assert "error" in tools.calculate("0 ** -1")


@pytest.mark.parametrize("expression", [
    "abc",
    "'a' * 5",
    "True + 1",
    "len([1, 2])",
    "1 +",
    "",
    "   ",
    None,
    "1" * 500,
], ids=["name", "string", "bool", "function-call", "incomplete", "empty", "spaces", "none", "too-long"])
def test_calculate_rejects_non_arithmetic_input(expression):
    r = tools.calculate(expression)
    assert isinstance(r, dict)
    assert "error" in r


def test_calculate_limits_very_large_numbers():
    assert "error" in tools.calculate("10 ** 18 * 10")
    assert "error" in tools.calculate("2 ** 1000")
    assert "error" in tools.calculate("(-8) ** 0.5")  # complex result is not a real number