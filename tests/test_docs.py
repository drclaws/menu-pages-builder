"""Tests of the documentation: the links of `README.md` and `docs/*.md`, and
the samples in them that the code must accept as they are written."""

import json
import re
import subprocess
import unittest
from pathlib import Path

from tests import fixtures, support

from menu_tools import _core, _page, _schema, _table, _words  # noqa: E402  (support prepares sys.path)

ROOT = support.ROOT
README = ROOT / "README.md"
DOCS = ROOT / "docs"

#: A Markdown link or image: [text](target).
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
#: The source of an HTML image: <img src="target">.
_SRC_RE = re.compile(r'\ssrc="([^"]+)"')
#: An HTML image tag, possibly over several lines.
_IMG_RE = re.compile(r"<img\b[^>]*>")
_FENCE_RE = re.compile(r"^```")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_JSON_BLOCK_RE = re.compile(r"^```json\n(.*?)^```$", re.M | re.S)


def documents() -> list:
    return [README, *sorted(DOCS.glob("*.md"))]


def prose_lines(path) -> list[str]:
    """The lines of a Markdown file outside its fenced code blocks."""
    lines, fenced = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return lines


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation other than
    '-' and '_' removed, every space a hyphen (hyphens are not collapsed)."""
    text = heading.strip().lower()
    text = "".join(char for char in text if char.isalnum() or char in "-_ ")
    return text.replace(" ", "-")


def anchors(path) -> set[str]:
    """The anchors of a file's headings; a repeated one gets -1, -2..."""
    found: set[str] = set()
    counts: dict[str, int] = {}
    for line in prose_lines(path):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        base = slug(match.group(2))
        count = counts.get(base, 0)
        counts[base] = count + 1
        found.add(base if count == 0 else f"{base}-{count}")
    return found


def tracked_files() -> set[str]:
    """The files of the repository, as paths from its root: the tracked
    ones when ROOT is the top of a git work tree, else every file on disk (a
    copy without git, or one unpacked inside another work tree)."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, check=True
        ).stdout.decode("utf-8")

    try:
        top = Path(git("rev-parse", "--show-toplevel").strip()).resolve()
        listed = git("ls-files", "-z") if top == ROOT else None
    except (OSError, subprocess.CalledProcessError):
        listed = None
    if listed is None:
        return {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()}
    return {name for name in listed.split("\0") if name}


def json_blocks(path) -> list:
    """Every ```json block of a file, parsed."""
    return [json.loads(block) for block in _JSON_BLOCK_RE.findall(path.read_text(encoding="utf-8"))]


def table_examples(path) -> list[dict]:
    return [block for block in json_blocks(path) if isinstance(block, dict) and "arms" in block]


def seat_centres(table: dict) -> dict[int, tuple[float, float]]:
    """Seat number -> the centre of the seat on the plan, px."""
    scheme = _table.guest_scheme(table, own_seats=[1], plan_text="")
    return {int(seat["number"]): (float(seat["cx"]), float(seat["cy"])) for seat in scheme["seats"]}


class LinkTest(unittest.TestCase):
    def test_every_relative_link_leads_to_a_file_and_a_heading(self):
        files = tracked_files()
        checked = 0
        for document in documents():
            for line in prose_lines(document):
                for target in [*_LINK_RE.findall(line), *_SRC_RE.findall(line)]:
                    if re.match(r"[a-z][a-z0-9+.-]*:", target):
                        continue  # an absolute address
                    with self.subTest(document=document.name, link=target):
                        path, _, anchor = target.partition("#")
                        linked = (document.parent / path).resolve() if path else document
                        name = linked.relative_to(ROOT).as_posix()
                        self.assertIn(name, files)
                        if anchor:
                            self.assertIn(anchor, anchors(linked))
                    checked += 1
        self.assertGreater(checked, 10)

    def test_the_readme_shows_every_image_with_a_text(self):
        text = "\n".join(prose_lines(README))
        images = _IMG_RE.findall(text)
        sources = []
        for image in images:
            match = _SRC_RE.search(image)
            self.assertIsNotNone(match, image)
            sources.append(match.group(1))
        shown = sorted(name for name in tracked_files() if name.startswith(".github/assets/"))
        self.assertTrue(shown)
        self.assertEqual(sorted(sources), shown)
        for image in images:
            with self.subTest(image=image):
                self.assertRegex(image, r'\salt="[^"]{20,}"')

    def test_the_readme_links_every_document(self):
        text = README.read_text(encoding="utf-8")
        for document in sorted(DOCS.glob("*.md")):
            with self.subTest(document=document.name):
                self.assertIn(f"](docs/{document.name})", text)

    def test_the_slugs_follow_github(self):
        self.assertEqual(slug("The guest's plan"), "the-guests-plan")
        self.assertEqual(slug("requirements and allergens"), "requirements-and-allergens")
        self.assertEqual(slug("A complete sample: Serbian, Latin script"), "a-complete-sample-serbian-latin-script")
        self.assertEqual(slug("`lang` - `strings`"), "lang---strings")


class JsonBlockTest(unittest.TestCase):
    def test_every_json_block_is_a_json_document(self):
        for document in documents():
            with self.subTest(document=document.name):
                self.assertIsInstance(json_blocks(document), list)


class LanguageSampleTest(unittest.TestCase):
    def setUp(self):
        samples = [block for block in json_blocks(DOCS / "languages.md") if "strings" in block]
        self.assertEqual(len(samples), 1)
        self.sample = samples[0]

    def test_the_sample_is_the_serbian_fixture(self):
        self.assertEqual(self.sample["lang"], "sr-Latn")
        self.assertEqual(list(self.sample["strings"]), list(_words.ENGLISH))
        self.assertEqual(self.sample["strings"], fixtures.SERBIAN_STRINGS)

    def test_the_sample_passes_the_checks_as_a_complete_menu(self):
        menu, guests = fixtures.serbian()
        menu.update(self.sample)
        report = _core.Report()
        _schema.check_data(menu, guests, report)
        self.assertEqual(report.errors, [])
        self.assertEqual([warning for warning in report.warnings if "strings" in warning], [])

    def test_the_sample_without_a_key_is_refused(self):
        menu, guests = fixtures.serbian()
        menu.update(self.sample)
        del menu["strings"]["you"]
        report = _core.Report()
        _schema.check_data(menu, guests, report)
        self.assertTrue(any("missing: you" in error for error in report.errors), report.errors)


class TableExampleTest(unittest.TestCase):
    def setUp(self):
        self.examples = table_examples(DOCS / "table-plan.md")
        self.assertEqual(len(self.examples), 2)

    def test_the_readme_shows_the_first_example(self):
        self.assertEqual(table_examples(README), self.examples[:1])

    def test_the_examples_pass_the_check(self):
        nineteen, eighteen = (_table.check_table(table) for table in self.examples)
        self.assertEqual((nineteen.errors, nineteen.total), ([], 19))
        self.assertEqual(len(nineteen.warnings), 2)  # the top row and the bottom row are squeezed
        self.assertTrue(all("squeezed" in warning for warning in nineteen.warnings))
        self.assertEqual(eighteen, _table.TableCheck([], [], 18))

    def test_the_seats_of_nineteen_are_where_the_text_says(self):
        seat = seat_centres(self.examples[0])
        x = {number: centre[0] for number, centre in seat.items()}
        y = {number: centre[1] for number, centre in seat.items()}
        self.assertEqual(y[8], y[1])
        self.assertEqual(x[7], x[12])
        self.assertEqual(y[13], y[11])
        self.assertEqual(y[14], y[10])
        self.assertEqual([y[n + 1] - y[n] for n in (8, 9, 10)], [42, 42, 42])
        self.assertEqual([x[n + 1] - x[n] for n in range(2, 7)], [40.5] * 5)

    def test_the_seats_of_eighteen_are_where_the_text_says(self):
        table = self.examples[1]
        seat = seat_centres(table)
        x = {number: centre[0] for number, centre in seat.items()}
        y = {number: centre[1] for number, centre in seat.items()}
        short = next(arm for arm in table["arms"] if arm["id"] == "short")
        self.assertEqual(x[8], short["x"] + short["width"] / 2)
        self.assertEqual([x[n] for n in range(13, 19)], [x[n] for n in range(7, 1, -1)])
        self.assertEqual(y[9], y[1])
        self.assertEqual(y[12], y[11])
        self.assertEqual([x[n + 1] - x[n] for n in range(2, 8)], [42] * 6)


class DataSampleTest(unittest.TestCase):
    def test_the_readme_sample_builds_without_a_warning(self):
        menu, guests = [block for block in json_blocks(README) if "arms" not in block][:2]
        report = _core.Report()
        index = _schema.check_data(menu, guests, report)
        self.assertEqual((report.errors, report.warnings), ([], []))
        trees = _page.build_trees(menu, guests, report)
        _schema.check_usage(index, menu, trees.usage, report)
        self.assertEqual((report.errors, report.warnings), ([], []))
        self.assertEqual((len(trees.guests), trees.staff is not None), (2, True))


if __name__ == "__main__":
    unittest.main()
