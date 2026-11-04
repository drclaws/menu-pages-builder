"""Tests of the facade of the engine of the build (`menu_tools/_core.py`)."""

import argparse
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _checks, _engine, _icon, _tokens, _values  # noqa: E402
from menu_tools import _core as core  # noqa: E402  (imported after sys.path is prepared)

#: The modules the facade takes its names from.
ENGINE_MODULES = (_engine, _values, _checks, _tokens, _icon)


class ExportsTest(unittest.TestCase):
    def test_every_exported_name_comes_from_the_engine(self):
        self.assertEqual(len(core.__all__), len(set(core.__all__)))
        aliases = {"SCHEMA_MISSING": (_checks, "MISSING")}
        missing = object()
        for name in core.__all__:
            with self.subTest(name=name):
                value = getattr(core, name)
                if name in aliases:
                    module, source = aliases[name]
                    self.assertIs(value, getattr(module, source))
                    continue
                origins = [module for module in ENGINE_MODULES
                           if getattr(module, name, missing) is value]
                self.assertTrue(origins, f"{name} is not a name of the engine")

    def test_names_with_two_meanings_come_from_the_right_module(self):
        self.assertIs(core.MISSING, _engine.MISSING)
        self.assertIs(core.SCHEMA_MISSING, _checks.MISSING)
        self.assertIsNot(core.MISSING, core.SCHEMA_MISSING)
        # of a style sheet
        self.assertIs(core.load_palette, _tokens.load_palette)

    def test_the_sentinels_are_what_the_helpers_return(self):
        report = core.Report()
        checker = core._Checker(report, "menu.json")
        self.assertIs(checker.value({}, "title", "string", ()), core.SCHEMA_MISSING)
        self.assertEqual(report.errors, [])
        with tempfile.TemporaryDirectory(prefix="menu-core-test-") as temporary:
            absent = Path(temporary) / "menu.json"
            self.assertIs(core.read_json(absent, report), core.MISSING)
        self.assertEqual(len(report.errors), 1)
        self.assertTrue(report.errors[0].endswith(": file not found"), report.errors)

    def test_exit_codes(self):
        self.assertEqual((core.EXIT_OK, core.EXIT_ERROR, core.EXIT_USAGE), (0, 1, 2))

    def test_the_argument_types_keep_good_values(self):
        self.assertEqual(core.token_prefix("heron"), "heron")
        self.assertEqual(core.parse_published_url("https://example.org/menu/"), "https://example.org/menu")
        self.assertEqual(core.base_path_argument("/menu"), "/menu")

    def test_the_argument_types_do_not_repeat_the_value(self):
        # a refused value may be private (a name in a prefix, credentials in
        # an address): the message names the problem, never the value
        cases = (
            (core.token_prefix, "Rosalind and Leopold"),
            (core.token_prefix, "Wendell" * 40),
            (core.parse_published_url, "https://wendell:hunter-secret@example.org/menu"),
            (core.parse_published_url, "ftp://bjarne-host.example.org/menu"),
            (core.parse_published_url, "https://example.org/menu?judy=1"),
            (core.base_path_argument, "/rosalind path"),
            (core.base_path_argument, "/leopold path"),
        )
        for convert, value in cases:
            with self.subTest(convert=convert.__name__, value=value):
                with self.assertRaises(argparse.ArgumentTypeError) as caught:
                    convert(value)
                message = str(caught.exception)
                self.assertTrue(message)
                self.assertNotIn(value, message)
                for word in re.findall(r"[A-Za-z]{4,}", value):
                    if word not in ("https", "example", "menu", "path"):
                        self.assertNotIn(word.lower(), message.lower())

    def test_the_reserved_tokens_are_refused_by_the_token_check(self):
        self.assertTrue(core.RESERVED_TOKENS)
        for token in core.RESERVED_TOKENS:
            with self.subTest(token=token):
                self.assertIsNotNone(core.check_token(token))
                self.assertIsNotNone(core.check_token(token.upper()))

    def test_the_colour_of_a_token_is_written_as_hex(self):
        self.assertEqual(core.hex_color((250, 247, 242)), "#faf7f2")
        self.assertTrue(issubclass(core.TokenError, ValueError))


if __name__ == "__main__":
    unittest.main()
