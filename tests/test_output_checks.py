"""Tests of the finished output checks (`menu_tools/_output.py`).

The output directories are made by hand: three pages and the files the
build copies into `assets/`.
"""

import inspect
import unittest
from pathlib import Path

from tests import support  # noqa: F401  (prepares sys.path)
from menu_tools import _core, _output  # noqa: E402

ROOT = support.ROOT
TOKENS = ("heron-4tx9", "crane-7m2p", "Rk4vTz8QwM2nLp6XhB9cJs")
#: An address of another part of the site, which the build does not write.
ELSEWHERE = "/other/x/"
#: The text of the pages; never part of a message.
SECRET_TEXT = "Rosalind sits next to Leopold"


def page(base: str, body: str = "") -> str:
    """A page that passes every output check under `base`."""
    assets = f"{base.rstrip('/')}/assets"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Dinner menu</title>\n"
        f'<link rel="icon" href="{assets}/favicon.svg" type="image/svg+xml">\n'
        f'<link rel="stylesheet" href="{assets}/app.css">\n'
        f'<script src="{assets}/app.js" defer></script>\n'
        "</head>\n"
        "<body>\n"
        f"<p>{SECRET_TEXT}</p>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


#: The line of `body` in a page from `page`.
BODY_LINE = page("/").splitlines().index("") + 1


class OutputChecksTest(support.TempDirTestCase):
    def make_output(self, base: str = "/", bodies: dict | None = None) -> Path:
        """A new output directory (each call its own)."""
        out = self.tmp / f"out-{len(list(self.tmp.iterdir()))}"
        for token in TOKENS:
            (out / token).mkdir(parents=True)
            text = page(base, (bodies or {}).get(token, ""))
            (out / token / "index.html").write_text(text, encoding="utf-8")
        _core.copy_assets(ROOT / "assets", out / "assets")
        palette = _core.load_palette(ROOT / "assets" / "app.css")
        (out / "assets" / "favicon.svg").write_bytes(_core.favicon_svg(palette))
        return out

    def problems(self, out: Path, base: str = "/", pages=TOKENS) -> list[str]:
        try:
            _output.check_menu_output(out, pages, base_path=base)
        except _core.OutputError as exc:
            for message in exc.errors:
                self.assertNotIn("Rosalind", message)
                for token in TOKENS:
                    self.assertNotIn(token.lower(), message.lower())
            return exc.errors
        return []

    def test_a_clean_output_passes(self):
        for base in ("/", "/menu"):
            with self.subTest(base=base):
                out = self.make_output(base)
                stats = _output.check_menu_output(out, TOKENS, base_path=base)
                self.assertEqual(stats.files, 6)
                self.assertEqual(sorted(path.name for path in (out / "assets").iterdir()),
                                 ["app.css", "app.js", "favicon.svg"])

    def test_a_style_attribute_is_refused(self):
        bodies = {
            "html": '<p style="color: red">Hello</p>',
            "svg": '<svg class="scheme" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill: red"/></svg>',
            "upper case": '<P STYLE="color: red">Hello</P>',
            "no value": "<div style>Hello</div>",
        }
        for name, body in bodies.items():
            with self.subTest(case=name):
                out = self.make_output(bodies={TOKENS[1]: body})
                self.assertEqual(
                    self.problems(out),
                    [f"…/index.html line {BODY_LINE}: {_output.STYLE_PROBLEM}"],
                )

    def test_an_attribute_that_only_ends_in_style_passes(self):
        out = self.make_output(bodies={TOKENS[0]: '<p data-style="x" class="style">Hello</p>'})
        self.assertEqual(self.problems(out), [])

    def test_the_text_style_is_no_attribute(self):
        out = self.make_output(bodies={TOKENS[0]: "<p>style=&quot;x&quot; is not markup</p>"})
        self.assertEqual(self.problems(out), [])

    def test_the_same_problem_in_several_files_is_one_line(self):
        body = '<p>one</p>\n<p style="margin: 0">two</p>\n<p style="margin: 0">three</p>'
        out = self.make_output(bodies={token: body for token in TOKENS})
        self.assertEqual(
            self.problems(out),
            [f"3 files: {_output.STYLE_PROBLEM}; first: …/index.html line {BODY_LINE + 1}"],
        )

    def test_every_problem_comes_in_one_error(self):
        out = self.make_output(bodies={TOKENS[0]: '<p style="color: red">x</p>'})
        (out / "notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(
            self.problems(out),
            [
                "notes.txt: unexpected file at the top of the output (the build writes the pages "
                "and assets/ only)",
                f"…/index.html line {BODY_LINE}: {_output.STYLE_PROBLEM}",
            ],
        )

    def test_an_extra_file_or_a_missing_page(self):
        out = self.make_output()
        (out / TOKENS[0] / "notes.html").write_text(page("/"), encoding="utf-8")
        (out / "assets" / "extra.json").write_text("{}", encoding="utf-8")
        problems = self.problems(out, pages=TOKENS + ("wren-5tc3",))
        self.assertEqual(
            problems,
            [
                "assets/extra.json: '.json' files must not be published",
                "…/notes.html: unexpected file (only index.html is allowed in the directory of a page)",
                "…/index.html: missing from the output",
                f"assets/extra.json: unexpected file ({_output.ASSETS_RULE})",
            ],
        )

    def test_assets_hold_the_style_sheet_the_script_and_the_icon_alone(self):
        self.assertEqual(_output.ASSETS_RULE, "only app.css, app.js and favicon.svg are published in assets/")
        # files a page could use from assets/: a note, a font, a picture
        out = self.make_output()
        (out / "assets" / "notes.txt").write_text("x", encoding="utf-8")
        (out / "assets" / "fonts").mkdir()
        (out / "assets" / "fonts" / "body.woff2").write_bytes(b"wOF2")
        (out / "assets" / "logo.png").write_bytes(b"\x89PNG")
        self.assertEqual(
            self.problems(out),
            [
                f"assets/fonts/: unexpected directory ({_output.ASSETS_RULE})",
                f"assets/logo.png: unexpected file ({_output.ASSETS_RULE})",
                f"assets/notes.txt: unexpected file ({_output.ASSETS_RULE})",
            ],
        )
        self.assertEqual(_output.asset_problems(self.make_output()), [])

    def test_a_link_outside_the_output_is_an_error(self):
        # another part of the site: outside the base path /menu, and a file
        # the output does not have at the top of the site; it is not part of
        # the page either
        not_a_part = f"…/index.html line {BODY_LINE}: <a href> {_output.LINK_RULE}"
        expected = {"/menu": "points outside the output", "/": "does not exist in the output"}
        for base, words in expected.items():
            with self.subTest(base=base):
                out = self.make_output(base, {TOKENS[0]: f'<a href="{ELSEWHERE}">Other</a>'})
                self.assertEqual(self.problems(out, base), [
                    f"…/index.html line {BODY_LINE}: <a href>: '/…' {words}",
                    not_a_part,
                ])
                # with the page's token in the address, that is a problem too
                out = self.make_output(base, {TOKENS[0]: f'<a href="{ELSEWHERE}{TOKENS[0]}/">Other</a>'})
                self.assertEqual(self.problems(out, base), [
                    f"…/index.html line {BODY_LINE}: <a href>: '/…' {words}",
                    not_a_part,
                    f"guests.json: guest #1: its token is in …/index.html; {_output.TOKEN_RULE}",
                ])

    def test_a_link_to_another_page_of_the_output_is_an_error(self):
        # the address resolves, but a page leads only to its own parts; the
        # address names the other page by its token as well
        for base in ("/", "/menu"):
            with self.subTest(base=base):
                link = f'<a href="{base.rstrip("/")}/{TOKENS[1]}/">Next</a>'
                self.assertEqual(
                    self.problems(self.make_output(base, {TOKENS[0]: link}), base),
                    [
                        f"…/index.html line {BODY_LINE}: <a href> {_output.LINK_RULE}",
                        f"guests.json: guest #2: its token is in …/index.html; {_output.TOKEN_RULE}",
                    ],
                )

    def test_a_link_to_a_part_of_the_same_page_passes(self):
        self.assertEqual(_output.LINK_RULE,
                         "must lead to a part of the same page ('#' and the id of an element on it)")
        bodies = {
            "the target after the link": '<a href="#s-food">Food</a>\n<section id="s-food"></section>',
            "the target before the link": '<h2 id="top">Menu</h2>\n<a href="#top">Top</a>',
            "an area of a map": '<map name="m" id="m"><area shape="rect" coords="0,0,1,1" href="#m" alt=""></map>',
            "a line of links": '<nav><a href="#a">A</a> <a href="#b">B</a></nav><p id="a">a</p><p id="b">b</p>',
        }
        for name, body in bodies.items():
            with self.subTest(case=name):
                for base in ("/", "/menu"):
                    self.assertEqual(self.problems(self.make_output(base, {TOKENS[0]: body}), base), [])

    def test_a_link_must_lead_to_an_element_of_its_own_page(self):
        self.assertEqual(_output.LINK_TARGET_PROBLEM, "names no element of the page")
        nowhere = f"…/index.html line {BODY_LINE}: <a href> {_output.LINK_TARGET_PROBLEM}"
        not_a_part = f"…/index.html line {BODY_LINE}: <a href> {_output.LINK_RULE}"
        cases = {
            "an id the page does not have": ('<a href="#nowhere">Nowhere</a>', [nowhere]),
            "an empty fragment": ('<a href="#">Top</a>', [nowhere]),
            "an id of another page": ('<a href="#elsewhere">Next</a>', [nowhere]),
            "no href": ("<a>Top</a>", [not_a_part]),
            "an empty href": ('<a href="">Top</a>',
                              [f"…/index.html line {BODY_LINE}: <a href>: the URL is empty", not_a_part]),
            "an area that leads elsewhere": (
                '<map name="m"><area shape="rect" coords="0,0,1,1" href="/other/" alt=""></map>',
                [f"…/index.html line {BODY_LINE}: <area href>: '/…' does not exist in the output",
                 f"…/index.html line {BODY_LINE}: <area href> {_output.LINK_RULE}"]),
            "an area without href": ('<map name="m"><area shape="rect" coords="0,0,1,1" alt=""></map>',
                                     [f"…/index.html line {BODY_LINE}: <area href> {_output.LINK_RULE}"]),
            "an address on another host": (
                '<a href="https://maps.example.org/nowhere" target="_blank" rel="noopener noreferrer">Map</a>',
                [f"…/index.html line {BODY_LINE}: <a href>: external link 'https://maps.example.org/…' "
                 "is not allowed", not_a_part]),
        }
        for name, (body, expected) in cases.items():
            with self.subTest(case=name):
                # the id of the last case is on another output page
                out = self.make_output(bodies={TOKENS[0]: body, TOKENS[1]: '<p id="elsewhere">x</p>'})
                problems = self.problems(out)
                self.assertEqual(problems, expected)
                for message in problems:
                    self.assertNotIn("nowhere", message)
                    self.assertNotIn("elsewhere", message)

    def test_the_same_link_problem_in_several_files_is_one_line(self):
        body = '<p>one</p>\n<a href="#nowhere">x</a>\n<a href="#">y</a>\n<a href="/other/">z</a>'
        out = self.make_output(bodies={token: body for token in TOKENS})
        self.assertEqual(
            _output.link_problems(out),
            [
                f"3 files: <a href> {_output.LINK_TARGET_PROBLEM}; first: …/index.html line {BODY_LINE + 1}",
                f"3 files: <a href> {_output.LINK_RULE}; first: …/index.html line {BODY_LINE + 3}",
            ],
        )
        self.assertEqual(_output.link_lines('<a href="#x">x</a>\n<b id="x"></b>\n<a href="#y">y</a>'),
                         [(3, f"<a href> {_output.LINK_TARGET_PROBLEM}")])

    def test_no_file_holds_a_token(self):
        self.assertEqual(_output.TOKEN_RULE, "a token is only the name of its page directory")
        # a page's own token, another one in upper case, the staff token in the style sheet
        out = self.make_output(bodies={TOKENS[0]: f"<p>{TOKENS[0]}</p>", TOKENS[2]: f"<p>{TOKENS[1].upper()}</p>"})
        with open(out / "assets" / "app.css", "a", encoding="utf-8") as handle:
            handle.write(f"/* {TOKENS[2].lower()} */\n")
        self.assertEqual(self.problems(out), [
            f"guests.json: guest #1: its token is in …/index.html; {_output.TOKEN_RULE}",
            f"guests.json: guest #2: its token is in …/index.html; {_output.TOKEN_RULE}",
            f"guests.json: guest #3: its token is in assets/app.css; {_output.TOKEN_RULE}",
        ])

    def test_a_token_in_several_files_is_one_line_with_the_number_of_its_record(self):
        out = self.make_output(bodies={token: f"<p>{TOKENS[1]}</p>" for token in TOKENS})
        (out / "assets" / "app.js").write_text(f"// {TOKENS[1]}\n", encoding="utf-8")
        expected = (f"guests.json: guest #7: its token is in 4 files of the output, first: …/index.html; "
                    f"{_output.TOKEN_RULE}")
        numbers = {TOKENS[0]: 4, TOKENS[1]: 7, TOKENS[2]: 9}
        self.assertEqual(_output.token_problems(out, TOKENS, numbers), [expected])
        with self.assertRaises(_core.OutputError) as caught:
            _output.check_menu_output(out, TOKENS, base_path="/", numbers=numbers)
        self.assertEqual(caught.exception.errors, [expected])
        # without the numbers a record is numbered by its place among the pages
        self.assertEqual(_output.token_problems(out, TOKENS),
                         [expected.replace("guest #7", "guest #2")])

    def test_a_resource_outside_the_output_is_an_error(self):
        for base in ("/", "/menu"):
            with self.subTest(base=base):
                out = self.make_output(base, {TOKENS[2]: f'<img src="{ELSEWHERE}x.png" alt="">'})
                problems = self.problems(out, base)
                self.assertEqual(len(problems), 1, problems)
                self.assertTrue(problems[0].startswith(f"…/index.html line {BODY_LINE}: <img src>"), problems)

    def test_the_check_takes_no_directory_of_the_site_but_the_base_path(self):
        # nothing outside the output is ever allowed
        self.assertEqual(list(inspect.signature(_output.check_menu_output).parameters),
                         ["out_dir", "pages", "base_path", "numbers"])

    def test_the_number_of_lines_is_limited(self):
        out = self.make_output(bodies={TOKENS[0]: '<p style="color: red">x</p>'})
        for number in range(30):
            (out / f"extra-{number:02}.txt").write_text("x", encoding="utf-8")
        problems = self.problems(out)
        limit = _core.MAX_REPORTED_PROBLEMS
        self.assertEqual(len(problems), limit + 1)
        self.assertEqual(problems[-1], "… and 6 more problem(s) in the output")

    def test_the_style_check_alone_on_a_document(self):
        document = '<p>a</p>\n<svg><g style="x"><rect STYLE="y"/></g></svg>\n<p data-style="z">b</p>'
        self.assertEqual(_output.style_lines(document), [2, 2])
        self.assertEqual(_output.shown_path("heron-4tx9/index.html"), "…/index.html")
        self.assertEqual(_output.shown_path("assets/app.css"), "assets/app.css")
        self.assertEqual(_output.shown_path("notes.txt"), "notes.txt")


if __name__ == "__main__":
    unittest.main()
