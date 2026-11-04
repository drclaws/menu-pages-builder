"""Tests of `build.py build` on the fixtures: the output, its checks, the
handling of `--out` and what the command prints."""

import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import fixtures, support

import build  # noqa: E402  (support prepares sys.path)
from menu_tools import _core  # noqa: E402

ROOT = support.ROOT

#: The only forms of a line of stderr that names a record.
RECORD_LINE = re.compile(r"(?:warning|error): guests\.json: guest #\d+: \S.*")
TEMPLATE_SUMMARY_LINE = re.compile(r"error: \d+ guest record\(s\): \S.*; first: guests\.json: guest #\d+")
OK_LINE = re.compile(r"build: OK -> \S+ \((\d+) page\(s\), (\d+) file\(s\) in total, \d+(?:\.\d)? (?:B|KiB|MiB)\)")

#: What `build` warns about for each fixture.
WARNINGS = {
    "mockup16": (
        "warning: menu.json: field 'table.seats' has 2 free seat(s): 12, 13 (shown as free on the staff page; "
        "list a seat that stays free on purpose in 'reservedSeats')\n"
    ),
    "reserved19": "",
    "plain": "",
    "parts": "",
}

STYLE_PROBLEM = "the attribute 'style' is not allowed (the styles live in assets/app.css)"


class BuildTestCase(support.TempDirTestCase):
    def write(self, name: str, menu: dict, guests: list) -> Path:
        return fixtures.write_data(self.tmp / "data" / name, menu, guests)

    def build(self, data: Path, out: Path, *extra: str):
        return support.run_main("build", "--data", data, "--out", out, *extra)

    def assert_quiet_about(self, result, menu: dict, guests: list) -> None:
        """No token, name or traceback in what the command printed, and every
        line that names a record has the form of a record label."""
        text = result.stdout + result.stderr
        self.assertNoPrivateData(text, fixtures.tokens(guests), fixtures.names(guests, menu))
        for line in result.stderr.splitlines():
            if "guest #" in line:
                self.assertTrue(
                    RECORD_LINE.fullmatch(line) or TEMPLATE_SUMMARY_LINE.fullmatch(line),
                    f"a line that names a record in another form: {line}",
                )
        for number in re.findall(r"\bguest #(\d+)\b", text):
            self.assertTrue(1 <= int(number) <= len(guests))

    def assert_layout(self, out: Path, guests: list) -> None:
        """Exactly a directory with index.html per record and three assets."""
        expected = sorted(f"{token}/index.html" for token in fixtures.tokens(guests))
        expected += ["assets/app.css", "assets/app.js", "assets/favicon.svg"]
        self.assertEqual(support.tree_files(out), sorted(expected))

    def leftovers(self, out: Path) -> list[str]:
        return sorted(path.name for path in out.parent.iterdir() if path.name.startswith(f".{out.name}."))


class FullBuildTest(BuildTestCase):
    def test_each_fixture_builds_in_process_and_as_a_script(self):
        work = self.tmp / "work"
        work.mkdir()
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                menu, guests = make()
                data = self.write(name, menu, guests)
                first, second = self.tmp / f"{name}-main", self.tmp / f"{name}-script"
                result = self.build(data, first)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, WARNINGS[name])
                script = support.run_script("build", "--data", data, "--out", second, cwd=work)
                self.assertEqual(script.returncode, 0, script.stderr)
                self.assertEqual(script.stderr, WARNINGS[name])
                for done, out in ((result, first), (script, second)):
                    self.assert_layout(out, guests)
                    self.assert_quiet_about(done, menu, guests)
                    lines = done.stdout.splitlines()
                    self.assertTrue(all(line.startswith("build: ") for line in lines), lines)
                    counts = OK_LINE.fullmatch(lines[-1])
                    self.assertIsNotNone(counts, lines[-1])
                    self.assertEqual(int(counts.group(1)), len(guests))
                    self.assertEqual(int(counts.group(2)), len(guests) + 3)
                self.assertEqual(support.tree_digest(first), support.tree_digest(second))
        self.assertEqual(list(work.iterdir()), [])

    def test_the_log_shows_counters_and_paths(self):
        menu, guests = fixtures.reserved19()
        data = self.write("reserved19", menu, guests)
        out = self.tmp / "site" / "menu"
        result = self.build(data, out, "--base-path", "/menu")
        self.assertEqual(result.returncode, 0, result.stderr)
        shown = _core.display_path(out)
        lines = result.stdout.splitlines()
        self.assertEqual(
            lines[:-1],
            [
                f"build: 12 guest record(s) + staff validated (data: {_core.display_path(data)})",
                f"build: wrote 13 page(s) to {shown}/<token>/",
                "build: base path /menu: the pages are at /menu/<token>/, the shared files at /menu/assets/",
                f"build: copied 2 asset file(s) to {shown}/assets/, favicon.svg generated from the design tokens",
            ],
        )
        self.assertRegex(lines[-1], rf"^build: OK -> {re.escape(shown)} \(13 page\(s\), 16 file\(s\) in total, ")

    def test_the_addresses_follow_the_base_path(self):
        menu, guests = fixtures.reserved19()
        data = self.write("reserved19", menu, guests)
        for base, prefix in (("/", ""), ("/menu", "/menu"), ("/a/b/", "/a/b")):
            with self.subTest(base=base):
                out = self.tmp / f"out{prefix.replace('/', '-')}"
                result = self.build(data, out, "--base-path", base)
                self.assertEqual(result.returncode, 0, result.stderr)
                page = (out / guests[0]["token"] / "index.html").read_text(encoding="utf-8")
                self.assertIn(f'<link rel="stylesheet" href="{prefix}/assets/app.css">', page)
                self.assertIn(f'<link rel="icon" href="{prefix}/assets/favicon.svg" type="image/svg+xml">', page)
                palette = _core.load_palette(ROOT / "assets" / "app.css")
                self.assertIn(f'<meta name="theme-color" content="{_core.hex_color(palette.surface)}">', page)
                self.assertEqual(
                    (out / "assets" / "favicon.svg").read_bytes(), _core.favicon_svg(palette)
                )

    def test_two_builds_are_identical(self):
        menu, guests = fixtures.reserved19()
        data = self.write("reserved19", menu, guests)
        digests = []
        for out in (self.tmp / "one", self.tmp / "two"):
            result = self.build(data, out, "--base-path", "/menu")
            self.assertEqual(result.returncode, 0, result.stderr)
            digests.append(support.tree_digest(out))
        self.assertEqual(digests[0], digests[1])
        self.assertEqual(len(digests[0]), 16)

    def test_a_second_build_replaces_the_first(self):
        menu, guests = fixtures.mockup16()
        data = self.write("mockup16", menu, guests)
        out = self.tmp / "dist"
        self.assertEqual(self.build(data, out).returncode, 0)
        before = support.tree_digest(out)
        # a record is gone: its page is gone as well
        del guests[3]
        fixtures.write_data(data, menu, guests)
        result = self.build(data, out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_layout(out, guests)
        self.assertNotEqual(support.tree_digest(out), before)
        self.assertEqual(self.leftovers(out), [])

    def test_the_leftovers_of_an_interrupted_build_are_removed(self):
        menu, guests = fixtures.plain()
        data = self.write("plain", menu, guests)
        out = self.tmp / "dist"
        stale = [self.tmp / ".dist.tmp-0123456789ab", self.tmp / ".dist.old-ba9876543210"]
        for path in stale:
            (path / guests[0]["token"]).mkdir(parents=True)
            (path / guests[0]["token"] / "index.html").write_text("<p>old</p>", encoding="utf-8")
        result = self.build(data, out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.leftovers(out), [])
        self.assertNotIn(guests[0]["token"], result.stdout + result.stderr)


class RefusalTest(BuildTestCase):
    def setUp(self):
        super().setUp()
        self.menu, self.guests = fixtures.reserved19()
        self.data = self.write("reserved19", self.menu, self.guests)

    def refused(self, out: Path, message: str):
        result = self.build(self.data, out)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, f"error: {message}\nbuild: failed\n")
        self.assert_quiet_about(result, self.menu, self.guests)
        return result

    def test_the_data_directory_and_what_is_inside_it(self):
        self.refused(self.data, "--out must not be the data directory; choose a separate output directory")
        self.refused(
            self.data / "dist",
            "--out must not lie inside the data directory (--data): the build never writes there; "
            "choose a separate output directory",
        )
        self.refused(self.data.parent, "--out must not be a parent of the data directory; choose a separate output directory")
        self.assertEqual(sorted(path.name for path in self.data.iterdir()), ["guests.json", "menu.json"])

    def test_the_code_directory(self):
        self.refused(ROOT / "assets" / "dist", "--out must not be inside the assets directory; choose a separate output directory")
        self.refused(ROOT, "--out must not be the code directory; choose a separate output directory")
        self.assertFalse((ROOT / "assets" / "dist").exists())

    def test_a_directory_of_somebody_else(self):
        out = self.tmp / "mine"
        out.mkdir()
        (out / "notes.txt").write_text("keep me", encoding="utf-8")
        self.refused(
            out,
            "refusing to replace --out: it does not look like a previous build output (unexpected at "
            "the top: 1 other entry; their names are not shown, they may be tokens); remove it manually "
            "or choose another --out",
        )
        self.assertEqual((out / "notes.txt").read_text(encoding="utf-8"), "keep me")
        self.assertEqual(self.leftovers(out), [])

    def test_more_than_a_build_writes_next_to_its_assets(self):
        # assets/ as a build writes it, an index page at the top and pages one
        # directory deeper: not a previous build
        out = self.tmp / "mine"
        (out / "assets").mkdir(parents=True)
        for name in ("app.css", "app.js"):
            (out / "assets" / name).write_text("x", encoding="utf-8")
        (out / "index.html").write_text("keep me", encoding="utf-8")
        (out / "pages" / "heron-4tx9").mkdir(parents=True)
        (out / "pages" / "heron-4tx9" / "index.html").write_text("keep me", encoding="utf-8")
        self.refused(
            out,
            "refusing to replace --out: it does not look like a previous build output (unexpected at "
            "the top: 1 directory and 1 other entry; their names are not shown, they may be tokens); "
            "remove it manually or choose another --out",
        )
        self.assertEqual((out / "index.html").read_text(encoding="utf-8"), "keep me")
        self.assertEqual(self.leftovers(out), [])


class FailingBuildTest(BuildTestCase):
    def setUp(self):
        super().setUp()
        self.menu, self.guests = fixtures.reserved19()
        self.data = self.write("reserved19", self.menu, self.guests)
        self.out = self.tmp / "dist"
        result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.before = support.tree_digest(self.out)

    def assert_kept(self) -> None:
        """The previous output is intact and nothing temporary is left."""
        self.assertEqual(support.tree_digest(self.out), self.before)
        self.assertEqual(self.leftovers(self.out), [])

    def code_with_template(self, line: str) -> Path:
        """A copy of the code whose template has `line` right after <body>."""
        code = self.tmp / "code"
        code.mkdir()
        for name in ("assets", "fragments"):
            shutil.copytree(ROOT / name, code / name)
        template = (ROOT / "template.html").read_text(encoding="utf-8")
        (code / "template.html").write_text(template.replace("<body>\n", f"<body>\n{line}\n", 1), encoding="utf-8")
        return code

    def test_a_page_with_a_style_attribute_fails(self):
        render_page = build.render_page

        def with_style(template, tree):
            return render_page(template, tree).replace("<main ", '<main style="margin: 0" ', 1)

        with mock.patch.object(build, "render_page", with_style):
            result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines(), ["build: 12 guest record(s) + staff validated "
                                                      f"(data: {_core.display_path(self.data)})"])
        # the first page in the order of the names of the directories
        first = sorted(fixtures.tokens(self.guests))[0]
        page = (self.out / first / "index.html").read_text(encoding="utf-8")
        line = page[: page.index("<main ")].count("\n") + 1
        self.assertEqual(
            result.stderr,
            f"error: 13 files: {STYLE_PROBLEM}; first: …/index.html line {line}\nbuild: failed with 1 error(s)\n",
        )
        self.assert_quiet_about(result, self.menu, self.guests)
        self.assert_kept()

    def test_a_template_problem_on_every_page_is_one_line(self):
        code = self.code_with_template("<p>{{noSuchField}}</p>")
        line = (code / "template.html").read_text(encoding="utf-8").splitlines().index("<p>{{noSuchField}}</p>") + 1
        with mock.patch.object(build, "CODE_DIR", code):
            result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr.splitlines(),
            [
                f"error: 13 guest record(s): template.html line {line}: field 'noSuchField' not found; "
                "first: guests.json: guest #1",
                "build: failed with 1 error(s)",
            ],
        )
        self.assert_quiet_about(result, self.menu, self.guests)
        self.assert_kept()

    def test_a_template_problem_on_one_page_names_its_record(self):
        code = self.code_with_template("<!-- if:isStaff --><p>{{noSuchField}}</p><!-- endif -->")
        with mock.patch.object(build, "CODE_DIR", code):
            result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 1)
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertRegex(lines[0], r"^error: guests\.json: guest #13: template\.html line \d+: field 'noSuchField' not found$")
        self.assert_quiet_about(result, self.menu, self.guests)
        self.assert_kept()

    def test_broken_data_names_the_records(self):
        self.guests[3]["seats"][0]["number"] = 4
        self.guests[5]["seats"][0]["requirements"] = ["nutz"]
        self.guests[12]["name"] = "Someone"
        fixtures.write_data(self.data, self.menu, self.guests)
        result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(lines[-1], "build: failed with 3 error(s)")
        self.assertEqual(
            [line.split(":", 3)[:3] for line in lines[:-1]],
            [["error", " guests.json", " guest #4"], ["error", " guests.json", " guest #6"],
             ["error", " guests.json", " guest #13"]],
        )
        self.assert_quiet_about(result, self.menu, self.guests)
        self.assert_kept()

    def with_link(self, link: str):
        """`render_page` of a broken template: `link` at the end of every page."""
        render_page = build.render_page

        def rendered(template, tree):
            return render_page(template, tree).replace("</main>", f"<p>{link}</p>\n</main>", 1)

        return mock.patch.object(build, "render_page", rendered)

    def test_a_link_outside_the_output_fails(self):
        # a page that leads to another part of the site, rendered by a broken
        # template: under the base path /menu the address lies outside the
        # output, at the top of the site it names no file of the output; it
        # is no part of the page either
        for base, words in (("/menu", "points outside the output"), ("/", "does not exist in the output")):
            with self.subTest(base=base):
                with self.with_link('<a href="/other/x/">Other</a>'):
                    result = self.build(self.data, self.out, "--base-path", base)
                self.assertEqual(result.returncode, 1)
                lines = result.stderr.splitlines()
                self.assertEqual(len(lines), 3, lines)
                self.assertRegex(lines[0], rf"^error: 13 files: <a href>: '/…' {words}; first: …/index\.html line \d+$")
                self.assertRegex(lines[1], r"^error: 13 files: <a href> must lead to a part of the same page "
                                           r"\('#' and the id of an element of the page\); first: …/index\.html "
                                           r"line \d+$")
                self.assertEqual(lines[2], "build: failed with 2 error(s)")
                self.assert_quiet_about(result, self.menu, self.guests)
                self.assert_kept()

    def test_a_link_to_no_part_of_the_page_fails(self):
        # an id the pages do not have and an empty fragment: one problem
        for link in ('<a href="#nowhere">Nowhere</a>', '<a href="#">Top</a>'):
            with self.subTest(link=link):
                with self.with_link(link):
                    result = self.build(self.data, self.out, "--base-path", "/menu")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout.splitlines(), ["build: 12 guest record(s) + staff validated "
                                                              f"(data: {_core.display_path(self.data)})"])
                lines = result.stderr.splitlines()
                self.assertEqual(len(lines), 2, lines)
                self.assertRegex(lines[0], r"^error: 13 files: <a href> names no element of the page; "
                                           r"first: …/index\.html line \d+$")
                self.assertEqual(lines[1], "build: failed with 1 error(s)")
                self.assertNotIn("nowhere", result.stderr)
                self.assert_quiet_about(result, self.menu, self.guests)
                self.assert_kept()

    def test_a_link_to_a_part_of_the_page_passes(self):
        # the cover of every page has the id of its section
        with self.with_link('<a href="#s-cover">Top</a>'):
            result = self.build(self.data, self.tmp / "with-a-link", "--base-path", "/menu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_a_token_written_into_the_data_fails(self):
        # a token typed into a text by mistake reads as a word to the checks
        # of the data; the check of the output finds it in any letter case
        tokens = [record["token"] for record in self.guests]

        def shared_text(menu, guests):
            # the card of the main course, on every guest page but the one that hides it
            menu["sections"][3]["widgets"][1]["text"] += f" Ask for {tokens[1]}."

        def note_to_a_guest(menu, guests):
            guests[3]["sections"] = {"signature": {"note": f"Your page: {tokens[3]}"}}

        def staff_reminder(menu, guests):
            menu["staff"]["reminder"] = f"The seat plan of {tokens[4].upper()} is final."

        cases = {
            "the shared text": (shared_text, "guests.json: guest #2: its token is in 11 files of the output, "
                                             "first: …/index.html"),
            "the note to a guest": (note_to_a_guest, "guests.json: guest #4: its token is in …/index.html"),
            "the staff reminder": (staff_reminder, "guests.json: guest #5: its token is in …/index.html"),
        }
        for name, (change, problem) in cases.items():
            with self.subTest(case=name):
                menu, guests = fixtures.reserved19()
                change(menu, guests)
                data = self.write(name.replace(" ", "-"), menu, guests)
                self.assertEqual(support.run_main("validate", "--data", data).returncode, 0)
                fresh = self.tmp / f"fresh-{name.replace(' ', '-')}"
                for out in (self.out, fresh):
                    result = self.build(data, out, "--base-path", "/menu")
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout.splitlines(), [
                        f"build: 12 guest record(s) + staff validated (data: {_core.display_path(data)})"])
                    self.assertEqual(result.stderr, f"error: {problem}; a token is only the name of the "
                                                    "directory of its page\nbuild: failed with 1 error(s)\n")
                    self.assert_quiet_about(result, menu, guests)
                self.assertFalse(fresh.exists())
                self.assertEqual(self.leftovers(fresh), [])
                self.assert_kept()

    def test_a_file_system_error_names_the_file_only_once_the_tokens_are_known(self):
        token = self.guests[0]["token"]
        failure = OSError(13, "Permission denied", str(self.out / token / "index.html"))
        with mock.patch.object(build, "check_out", side_effect=failure):
            early = self.build(self.data, self.out)
        self.assertEqual(early.stderr, "error: Permission denied\nbuild: failed\n")
        with mock.patch.object(_core, "write_pages", side_effect=failure):
            late = self.build(self.data, self.out)
        self.assertEqual(
            late.stderr.splitlines(),
            [f"error: Permission denied: {_core.display_path(self.out)}/…/index.html", "build: failed"],
        )
        for result in (early, late):
            self.assertEqual(result.returncode, 1)
            self.assert_quiet_about(result, self.menu, self.guests)
        self.assert_kept()

    def test_an_icon_in_the_assets_of_the_code_is_refused(self):
        code = self.code_with_template("")
        (code / "assets" / "Favicon.svg").write_text("<svg></svg>", encoding="utf-8")
        with mock.patch.object(build, "CODE_DIR", code):
            result = self.build(self.data, self.out)
        self.assertEqual(
            result.stderr,
            "error: assets/Favicon.svg of the code collides with the icon that the build generates from "
            "the design tokens; remove it\nbuild: failed\n",
        )
        self.assert_kept()

    def test_another_file_in_the_assets_of_the_code_is_not_published(self):
        code = self.code_with_template("")
        (code / "assets" / "notes.txt").write_text("a note of the code", encoding="utf-8")
        with mock.patch.object(build, "CODE_DIR", code):
            result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "error: assets/notes.txt: unexpected file (only app.css, app.js and favicon.svg are published in "
            "assets/)\nbuild: failed with 1 error(s)\n",
        )
        self.assert_quiet_about(result, self.menu, self.guests)
        self.assert_kept()

    def test_design_tokens_that_cannot_be_read(self):
        code = self.code_with_template("")
        css = (code / "assets" / "app.css").read_text(encoding="utf-8")
        (code / "assets" / "app.css").write_text(css.replace("--color-surface:", "--color-surfaces:", 1), encoding="utf-8")
        with mock.patch.object(build, "CODE_DIR", code):
            result = self.build(self.data, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "error: assets/app.css: design token '--color-surface' is not defined on :root (the colour of "
            "the browser interface and the icon are taken from the design tokens)\nbuild: failed\n",
        )
        self.assert_kept()


if __name__ == "__main__":
    unittest.main()
