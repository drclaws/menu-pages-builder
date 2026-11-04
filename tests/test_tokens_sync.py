"""The design tokens of the menu are those of the invitations, value for value.

The comments differ, so values are compared, never text: the custom
properties (and the `color-scheme` of the theme) of every `:root` rule, at the
top level and inside each `@media` / `@supports` block (a context of its
own), read by the small parser below.
Section 1 of `assets/app.css` must equal the reference exactly; the menu adds
only the tokens of `MENU_TOKENS`, and only in block 1a.

The reference is the style sheet of the invitations in the `site/` submodule,
at the pinned commit: only its `:root` rules are read, comments aside.
Without the submodule the tests fail (they are not skipped).
"""

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MENU_CSS = ROOT / "assets" / "app.css"
REFERENCE = ROOT / "site" / "assets" / "app.css"
REFERENCE_MISSING = (
    "the reference site/assets/app.css is missing (the invitations builder is "
    "not checked out in site/): run git submodule update --init --recursive"
)

#: The tokens of the menu only (block "1a. Menu tokens").
MENU_TOKENS = frozenset({
    "--color-flag",
    "--color-flag-bg",
    "--color-flag-line",
    "--color-flag-text",
    "--color-on-flag",
    "--color-couple-line",
    "--color-seat-1",
    "--color-seat-2",
    "--color-seat-3",
    "--line-width-seat",
    "--line-width-flag",
    "--seat-ring-opacity",
    "--seating-bleed-gap",
    "--scheme-font-number",
    "--scheme-font-label",
    "--scheme-font-badge",
    "--scheme-font-couple",
    "--scheme-tracking-couple",
    "--scheme-font-weight-strong",
    "--line-width-flag-print",
    "--seat-ring-opacity-print",
    "--sets-tab-min",
    "--label-padding-block",
    "--number-box-width",
    "--section-nav-padding-block",
    "--section-nav-size",
    "--section-nav-block-size",
    "--section-nav-gap",
})

#: Plain properties of `:root` compared like tokens: the theme is part of the design.
ROOT_PROPERTIES = frozenset({"color-scheme"})

COMMENT_RE = re.compile(r"/\*.*?(?:\*/|\Z)", re.DOTALL)
ROOT_RE = re.compile(r"(?<![\w-]):root\s*\{")
AT_RULE_RE = re.compile(r"@(media|supports)\b([^{;]*)\{")
SECTION_RE = re.compile(r"^/\* =+\n   (\d+a?)\. ", re.MULTILINE)
COLOUR_RE = re.compile(r"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|rgba?\([^()]*\)"
                       r"|var\(--[\w-]+(?:,[^()]*)?\)")


def split_declarations(body):
    """Split a rule body at the `;` outside brackets and strings."""
    parts = []
    depth = 0
    quote = ""
    start = 0
    for index, char in enumerate(body):
        if quote:
            if char == quote and body[index - 1] != "\\":
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    return parts


def block_end(text, start):
    """The index just past the `}` closing the block whose body starts at `start`."""
    depth = 1
    end = start
    while end < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[end], 0)
        end += 1
    return end


def token_contexts(css, context=""):
    """{context: {token: value}} of the `:root` rules of a style sheet.

    Tokens are the custom properties and the properties of `ROOT_PROPERTIES`.
    The context is "" at the top level, otherwise the at-rule preludes with
    their whitespace collapsed ("@media (min-width: 48em)"); nested blocks
    join their preludes. Values have their whitespace collapsed; when a token
    is declared twice in one context the last one wins. Contexts without
    tokens are left out.
    """
    text = COMMENT_RE.sub(" ", css)
    contexts = {}
    depth = 0
    position = 0
    while position < len(text):
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == ":" and depth == 0 and ROOT_RE.match(text, position):
            start = ROOT_RE.match(text, position).end()
            end = block_end(text, start)
            for declaration in split_declarations(text[start:end - 1]):
                name, colon, value = declaration.partition(":")
                name = name.strip()
                if colon and (name.startswith("--") or name in ROOT_PROPERTIES):
                    contexts.setdefault(context, {})[name] = " ".join(value.split())
            position = end
            continue
        elif char == "@" and depth == 0 and AT_RULE_RE.match(text, position):
            match = AT_RULE_RE.match(text, position)
            end = block_end(text, match.end())
            prelude = " ".join(("@%s %s" % (match.group(1), match.group(2))).split())
            inner = " ".join((context + " " + prelude).split())
            for key, tokens in token_contexts(text[match.end():end - 1], inner).items():
                contexts.setdefault(key, {}).update(tokens)
            position = end
            continue
        position += 1
    return contexts


def differences(mine, reference):
    """What `mine` lacks or changes against `reference`, and what it adds."""
    problems = []
    for context in sorted(set(reference) | set(mine)):
        where = context or ":root"
        expected = reference.get(context, {})
        actual = mine.get(context, {})
        if context not in mine:
            problems.append("%s: context missing" % where)
        elif context not in reference:
            problems.append("%s: context not in the reference" % where)
        for name in sorted(set(expected) | set(actual)):
            if name not in actual:
                problems.append("%s: %s missing" % (where, name))
            elif name not in expected:
                problems.append("%s: %s not in the reference" % (where, name))
            elif actual[name] != expected[name]:
                problems.append("%s: %s is %r, the reference has %r"
                                % (where, name, actual[name], expected[name]))
    return problems


def sections(css):
    """{"1": text, "1a": text, ...}: each numbered section up to the next one."""
    marks = list(SECTION_RE.finditer(css))
    return {mark.group(1): css[mark.start():marks[i + 1].start() if i + 1 < len(marks) else len(css)]
            for i, mark in enumerate(marks)}


def without_menu_tokens(contexts):
    trimmed = {}
    for context, tokens in contexts.items():
        kept = {name: value for name, value in tokens.items() if name not in MENU_TOKENS}
        if kept:
            trimmed[context] = kept
    return trimmed


class TokenParserTest(unittest.TestCase):
    def test_contexts_values_and_comments(self):
        css = """
            /* :root { --commented: 1; } */
            :root {
              --a: 1px;
              --b: var(--a,
                       2px) ;
              color-scheme: only light;
            }
            .x { --not-root: 1; }
            html:root { --not-bare-root: 1; }
            @media (min-width:   48em) {
              :root { --a: 2px; }
              .y { --not-root: 2; }
            }
            @supports (height: 100svh) { :root { --c: "a;b"; --d: calc(1px + (2px)); } }
            @media print { .z { --e: 1; } }
            @media screen { @supports (display: grid) { :root { --f: 1; } } }
            @keyframes k { from { opacity: 0; } }
            :root { --a: 3px; }
        """
        self.assertEqual(token_contexts(css), {
            "": {"--a": "3px", "--b": "var(--a, 2px)", "color-scheme": "only light"},
            "@media (min-width: 48em)": {"--a": "2px"},
            "@supports (height: 100svh)": {"--c": '"a;b"', "--d": "calc(1px + (2px))"},
            "@media screen @supports (display: grid)": {"--f": "1"},
        })

    def test_no_root_rule_gives_no_context(self):
        self.assertEqual(token_contexts(".a { --b: 1; } @media print { .c { color: red; } }"), {})

    def test_differences_name_the_token_and_the_context(self):
        reference = {"": {"--a": "1", "--b": "2"}, "@media print": {"--a": "3"}}
        mine = {"": {"--a": "1", "--b": "5", "--c": "4"}}
        self.assertEqual(differences(mine, reference), [
            ":root: --b is '5', the reference has '2'",
            ":root: --c not in the reference",
            "@media print: context missing",
            "@media print: --a missing",
        ])
        self.assertEqual(differences(reference, reference), [])


class TokensSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not REFERENCE.is_file():
            raise AssertionError(REFERENCE_MISSING)
        cls.css = MENU_CSS.read_text(encoding="utf-8")
        cls.reference = token_contexts(REFERENCE.read_text(encoding="utf-8"))
        cls.menu = token_contexts(cls.css)
        cls.sections = sections(cls.css)

    def test_the_reference_reads(self):
        self.assertIn("", self.reference)
        self.assertGreater(len(self.reference[""]), 100)
        self.assertIn("--color-accent", self.reference[""])
        self.assertGreaterEqual(len(self.reference), 2)
        # the one fixed light theme is compared like a token
        self.assertEqual(self.reference[""]["color-scheme"], "only light")
        self.assertEqual(self.menu[""]["color-scheme"], "only light")

    def test_section_1_is_the_reference_value_for_value(self):
        self.assertIn("1", self.sections)
        self.assertEqual(differences(token_contexts(self.sections["1"]), self.reference), [])

    def test_the_same_contexts(self):
        self.assertEqual(sorted(self.menu), sorted(self.reference))

    def test_every_token_of_the_reference_has_its_value(self):
        self.assertEqual(differences(without_menu_tokens(self.menu), self.reference), [])

    def test_the_menu_adds_exactly_its_own_tokens(self):
        added = {(context, name) for context, tokens in self.menu.items() for name in tokens
                 if name not in self.reference.get(context, {})}
        self.assertEqual({name for _context, name in added}, set(MENU_TOKENS))
        # none of them is a token of the invitations under another meaning
        every = {name for tokens in self.reference.values() for name in tokens}
        self.assertEqual(MENU_TOKENS & every, frozenset())

    def test_the_menu_tokens_live_only_in_block_1a(self):
        self.assertIn("1a", self.sections)
        block = token_contexts(self.sections["1a"])
        self.assertEqual({name for tokens in block.values() for name in tokens}, set(MENU_TOKENS))
        self.assertIn("", block)
        for context in block:
            with self.subTest(context=context or ":root"):
                self.assertIn(context, self.reference)
        for number, text in self.sections.items():
            if number not in ("1", "1a"):
                with self.subTest(section=number):
                    self.assertEqual(token_contexts(text), {})

    def test_a_changed_or_missing_token_is_caught(self):
        section = self.sections["1"]
        for old, new, expected in (
            ("--color-accent: #1f5673;", "--color-accent: #1f5674;", ":root: --color-accent is"),
            ("--events-tab-min: 11rem;", "", ":root: --events-tab-min missing"),
            ("--duration-slow: 0.01ms;", "--duration-slow: 0ms;",
             "@media (prefers-reduced-motion: reduce): --duration-slow is"),
            ("--bp-layout: 48em;", "--bp-layout: 48em; --extra: 1;", ":root: --extra not in the reference"),
            ("color-scheme: only light;", "color-scheme: light dark;", ":root: color-scheme is"),
        ):
            with self.subTest(token=old):
                self.assertEqual(section.count(old), 1)
                problems = differences(token_contexts(section.replace(old, new)), self.reference)
                self.assertEqual(len(problems), 1, problems)
                self.assertTrue(problems[0].startswith(expected), problems)

    def test_menu_colours_use_the_formats_of_the_palette(self):
        tokens = self.menu[""]
        for name in sorted(MENU_TOKENS):
            if name.startswith("--color-"):
                with self.subTest(token=name):
                    self.assertRegex(tokens[name], r"\A(?:%s)\Z" % COLOUR_RE.pattern)


class MissingReferenceTest(unittest.TestCase):
    def test_without_the_submodule_the_tests_fail_with_a_message(self):
        absent = ROOT / "site" / "assets" / "absent.css"
        with mock.patch.object(sys.modules[__name__], "REFERENCE", absent):
            with self.assertRaises(AssertionError) as caught:
                TokensSyncTest.setUpClass()
        self.assertEqual(str(caught.exception), REFERENCE_MISSING)
        self.assertIn("git submodule update --init --recursive", REFERENCE_MISSING)


if __name__ == "__main__":
    unittest.main()
