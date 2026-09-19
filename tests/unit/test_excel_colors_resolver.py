"""Tests for the pure Excel per-employee color resolver.

resolve_excel_employee_colors() decides which (bg, font) pair the
GET /api/export_excel endpoint paints for each employee: a custom override
saved by the user, a default extracted from the master workbook "HORARIO
2026.xlsx" (keyed by first name), or a sequential palette fallback.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from excel_colors import (  # noqa: E402
    EXCEL_COLOR_DEFAULTS,
    EXCEL_COLOR_PALETTE,
    excel_font_color_for_fill,
    normalize_hex_color,
    resolve_excel_employee_colors,
)


class TestDefaultMatching:
    def test_exact_first_name_match(self):
        result = resolve_excel_employee_colors(["Jeison"], {})
        assert result["Jeison"] == {"bg": "663300", "font": "FFFFFF", "source": "default"}

    def test_full_name_matches_leading_first_name(self):
        result = resolve_excel_employee_colors(["Jeison Aleman Tijerino"], {})
        assert result["Jeison Aleman Tijerino"]["bg"] == "663300"
        assert result["Jeison Aleman Tijerino"]["font"] == "FFFFFF"
        assert result["Jeison Aleman Tijerino"]["source"] == "default"

    def test_multi_word_default_key_prefers_longest_match(self):
        # "Juan David" is a two-word default key; a single-word "Juan" key
        # does not exist, but the match must still pick the full key, not
        # accidentally split on the first word.
        result = resolve_excel_employee_colors(["Juan David Alfaro Vargas"], {})
        assert result["Juan David Alfaro Vargas"]["bg"] == "BF9000"
        assert result["Juan David Alfaro Vargas"]["font"] == "FFFFFF"
        assert result["Juan David Alfaro Vargas"]["source"] == "default"

    def test_accent_and_case_insensitive_match(self):
        result = resolve_excel_employee_colors(["RANDALL Nuñez Arauz"], {})
        assert result["RANDALL Nuñez Arauz"]["bg"] == "BFBFBF"
        assert result["RANDALL Nuñez Arauz"]["source"] == "default"

    def test_unrelated_name_does_not_match_a_default(self):
        # "Ileananas" starts with "Ileana" as a *string prefix* but not as a
        # leading-word prefix (no space boundary) — must NOT match.
        result = resolve_excel_employee_colors(["Ileananas Gomez"], {})
        assert result["Ileananas Gomez"]["source"] == "palette"


class TestPaletteFallback:
    def test_unknown_names_get_distinct_palette_colors(self):
        names = ["Zoraida Nueva", "Wilbert Extra"]
        result = resolve_excel_employee_colors(names, {})
        assert result["Zoraida Nueva"]["source"] == "palette"
        assert result["Wilbert Extra"]["source"] == "palette"
        assert result["Zoraida Nueva"]["bg"] != result["Wilbert Extra"]["bg"]
        assert result["Zoraida Nueva"]["bg"] == EXCEL_COLOR_PALETTE[0]
        assert result["Wilbert Extra"]["bg"] == EXCEL_COLOR_PALETTE[1]

    def test_palette_fallback_font_is_auto_contrast(self):
        result = resolve_excel_employee_colors(["Alguien Nuevo"], {})
        bg = result["Alguien Nuevo"]["bg"]
        assert result["Alguien Nuevo"]["font"] == excel_font_color_for_fill(bg)


class TestCustomOverrides:
    def test_custom_overrides_default_by_exact_name(self):
        custom = {"Jeison Aleman Tijerino": {"bg": "112233", "font": "AABBCC"}}
        result = resolve_excel_employee_colors(["Jeison Aleman Tijerino"], custom)
        assert result["Jeison Aleman Tijerino"] == {
            "bg": "112233",
            "font": "AABBCC",
            "source": "custom",
        }

    def test_custom_bg_only_gets_auto_contrast_font(self):
        custom = {"Fabian Ortiz Morales": {"bg": "000000"}}
        result = resolve_excel_employee_colors(["Fabian Ortiz Morales"], custom)
        assert result["Fabian Ortiz Morales"]["bg"] == "000000"
        assert result["Fabian Ortiz Morales"]["font"] == "FFFFFF"
        assert result["Fabian Ortiz Morales"]["source"] == "custom"

    def test_custom_font_only_keeps_default_bg(self):
        custom = {"Jeison Aleman Tijerino": {"font": "00FF00"}}
        result = resolve_excel_employee_colors(["Jeison Aleman Tijerino"], custom)
        assert result["Jeison Aleman Tijerino"]["bg"] == "663300"  # default bg preserved
        assert result["Jeison Aleman Tijerino"]["font"] == "00FF00"
        assert result["Jeison Aleman Tijerino"]["source"] == "custom"

    def test_custom_only_applies_to_exact_name_key(self):
        # A custom entry keyed by the short first name must NOT leak onto a
        # different employee whose full name merely starts with it.
        custom = {"Jeison": {"bg": "ABCDEF"}}
        result = resolve_excel_employee_colors(["Jeison Aleman Tijerino"], custom)
        assert result["Jeison Aleman Tijerino"]["source"] == "default"
        assert result["Jeison Aleman Tijerino"]["bg"] == "663300"

    def test_invalid_hex_is_ignored(self):
        custom = {"Jeison Aleman Tijerino": {"bg": "not-a-color", "font": "zzzzzz"}}
        result = resolve_excel_employee_colors(["Jeison Aleman Tijerino"], custom)
        # Falls back entirely to the default since both custom values are invalid.
        assert result["Jeison Aleman Tijerino"]["source"] == "default"
        assert result["Jeison Aleman Tijerino"]["bg"] == "663300"
        assert result["Jeison Aleman Tijerino"]["font"] == "FFFFFF"


class TestHexNormalization:
    def test_accepts_hash_prefixed_hex(self):
        assert normalize_hex_color("#FfAaBb") == "FFAABB"

    def test_accepts_bare_hex(self):
        assert normalize_hex_color("ffaabb") == "FFAABB"

    def test_accepts_argb_hex(self):
        assert normalize_hex_color("FFffaabb") == "FFAABB"

    def test_rejects_invalid_length(self):
        assert normalize_hex_color("FFF") is None

    def test_rejects_non_hex_chars(self):
        assert normalize_hex_color("GGGGGG") is None

    def test_rejects_empty(self):
        assert normalize_hex_color("") is None
        assert normalize_hex_color(None) is None


def test_all_seed_defaults_present():
    expected_names = {
        "Antonio", "Fabian", "Ileana", "Jeison", "Jensy", "Juan David",
        "Maikel", "Natanael", "Randall", "Steven", "Tomas", "Alejandro",
        "Practicante", "Refuerzo", "Angel", "Eligio", "Keilor",
    }
    assert expected_names.issubset(EXCEL_COLOR_DEFAULTS.keys())
