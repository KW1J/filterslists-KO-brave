"""Unit tests for scripts/build.py (stdlib unittest, no network).

Run: python3 -m unittest discover -s tests -v
"""

import importlib.util
import os
import sys
import unittest

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("build", os.path.join(ROOT, "scripts", "build.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def conv(line):
    return build.convert_rule(line)


class ConvertRuleTest(unittest.TestCase):
    def test_style_injection(self):
        new, kind = conv("banhub.xyz#$#html{ overflow: visible !important; }")
        self.assertEqual(kind, "style")
        self.assertEqual(new, "banhub.xyz##html:style(overflow: visible !important;)")

    def test_multiple_declarations_keep_order(self):
        new, _ = conv(
            "aagag.com#$#.la { height: 75px !important; width: 75px !important; visibility: hidden !important; }"
        )
        self.assertEqual(
            new,
            "aagag.com##.la:style(height: 75px !important; width: 75px !important; visibility: hidden !important;)",
        )

    def test_calc_and_quotes_survive(self):
        new, _ = conv('yes24.com#$##yWelTopMid .yWelTodayBook { width: calc(100% - 240px) !important; }')
        self.assertEqual(new, "yes24.com###yWelTopMid .yWelTodayBook:style(width: calc(100% - 240px) !important;)")

    def test_procedural_remove(self):
        new, kind = conv("chzzk.naver.com#$?#.a > .b { remove: true; }")
        self.assertEqual(kind, "remove")
        self.assertEqual(new, "chzzk.naver.com##.a > .b:remove()")

    def test_procedural_style_body(self):
        new, kind = conv("search.daum.net#$?##aside > div { margin-top: 0px !important; }")
        self.assertEqual(kind, "style")
        self.assertEqual(new, "search.daum.net###aside > div:style(margin-top: 0px !important;)")

    def test_braces_inside_regex_attribute(self):
        line = 'm.fmkorea.com#$?#body div:matches-css(height: /^[0-9]{2,3}/) { remove: true; }'
        new, kind = conv(line)
        self.assertEqual(kind, "remove")
        self.assertEqual(new, "m.fmkorea.com##body div:matches-css(height: /^[0-9]{2,3}/):remove()")

    def test_selector_list_split(self):
        new, _ = conv("edufindkorea.com#$##a > div, #b > div { width: 100% !important; }")
        self.assertEqual(
            new,
            "edufindkorea.com###a > div:style(width: 100% !important;), edufindkorea.com###b > div:style(width: 100% !important;)",
        )

    def test_comma_inside_pseudo_not_split(self):
        new, _ = conv("example.com#$#.ad:has(a, b) { display: none !important; }")
        self.assertEqual(new, "example.com##.ad:has(a, b):style(display: none !important;)")

    def test_exception_style(self):
        new, kind = conv("example.com#@$#.ad { display: block !important; }")
        self.assertEqual(kind, "exception-style")
        self.assertEqual(new, "example.com#@#.ad:style(display: block !important;)")

    def test_exception_remove(self):
        new, kind = conv("example.com#@$?#.ad { remove: true; }")
        self.assertEqual(kind, "exception-remove")
        self.assertEqual(new, "example.com#@#.ad:remove()")

    def test_plain_rules_untouched(self):
        for line in (
            "||adflow.kr^",
            "||priel.co.kr^$third-party",
            "example.com##.ad",
            "example.com#?#.ad:has-text(AD)",
            "example.com##.ad:upward(2)",
            "/yasyadong[0-9]+\\.tv/##.top-ad-padding",
        ):
            new, kind = conv(line)
            self.assertIsNone(new, line)
            self.assertEqual(kind, "no-marker")

    def test_broken_bodies_rejected(self):
        self.assertIsNone(conv("example.com#$#.ad")[0])          # no { }
        self.assertIsNone(conv("example.com#$#{ color: red; }")[0])  # empty selector
        self.assertIsNone(conv("example.com#$#.ad {  }")[0])      # empty body


class BuildTest(unittest.TestCase):
    SRC = """! Title: filterslists-KO (uBO)
! Version: 2026.20763.0
! Homepage: https://github.com/FilteringDev/filterslists-KO

||adflow.kr^
example.com#$#.ad { display: none !important; }
example.com#$?#.b { remove: true; }
"""

    def test_header_and_stats(self):
        out, stats, version = build.build(self.SRC)
        self.assertEqual(version, "2026.20763.0")
        self.assertEqual(stats["rules_in"], 3)
        self.assertEqual(stats["converted_style"], 1)
        self.assertEqual(stats["converted_remove"], 1)
        self.assertEqual(stats["kept_unconverted"], 0)

        lines = out.splitlines()
        self.assertEqual(lines[0], "! Title: filterslists-KO (Brave)")
        self.assertIn("! Version: 2026.20763.0", lines)
        self.assertIn("! Expires: 1 day", lines)
        self.assertTrue(any(ln.startswith("! Homepage: https://github.com/KW1J/") for ln in lines))
        self.assertTrue(any("GPL-3.0" in ln for ln in lines))
        # upstream metadata replaced, not duplicated
        self.assertEqual(sum(1 for ln in lines if ln.startswith("! Version:")), 1)
        self.assertEqual(sum(1 for ln in lines if ln.startswith("! Title:")), 1)
        self.assertIn("||adflow.kr^", lines)
        self.assertIn("example.com##.ad:style(display: none !important;)", lines)
        self.assertIn("example.com##.b:remove()", lines)

    def test_version_override(self):
        _, _, version = build.build(self.SRC, "9999.1.2")
        self.assertEqual(version, "9999.1.2")

    def test_non_ascii_preserved(self):
        src = "! 설명: 한국어 주석\nexample.com##.광고\n"
        out, _, _ = build.build(src)
        self.assertIn("! 설명: 한국어 주석", out)
        self.assertIn("example.com##.광고", out)


if __name__ == "__main__":
    unittest.main()
