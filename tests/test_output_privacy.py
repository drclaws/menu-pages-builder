"""Privacy of the finished pages, read file by file after a build.

* no record's token, the staff record included, is in any output file, its
  own page included: a token is only the name of its page directory;
* `{token}` is left nowhere;
* a record's name (and each of its seats' names) is on its own page and on
  the staff page alone;
* the dietary note and allergen labels are on the staff page alone.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import fixtures, support


def data_sets() -> dict[str, tuple[dict, list]]:
    """Every data set the pages are built from, by name: the fixtures and
    the examples."""
    sets = {f"fixture {name}": make() for name, make in fixtures.SETS.items()}
    for directory in sorted((support.ROOT / "examples").iterdir()):
        sets[f"examples/{directory.name}"] = tuple(
            json.loads((directory / name).read_text(encoding="utf-8")) for name in ("menu.json", "guests.json")
        )
    return sets


def record_names(guests: list) -> dict[str, set[int]]:
    """Name -> the numbers of the records that hold it (as the record's name
    or a seat's name)."""
    names: dict[str, set[int]] = {}
    for number, record in enumerate(guests, start=1):
        found = {record.get("name")} | {seat.get("name") for seat in record.get("seats", [])}
        for name in found - {None, ""}:
            names.setdefault(name, set()).add(number)
    return names


def labels(menu: dict) -> set[str]:
    """The dietary note labels and tags and the allergen labels."""
    found = set()
    for requirement in (menu.get("requirements") or {}).values():
        found |= {requirement["label"], requirement.get("tag", "")}
    for allergen in (menu.get("allergens") or {}).values():
        found.add(allergen["label"])
    return found - {""}


def privacy_problems(out: Path, menu: dict, guests: list) -> list[str]:
    """What the finished output shows that it must not, as readable lines."""
    problems: list[str] = []
    files = {name: (out / name).read_text(encoding="utf-8") for name in support.tree_files(out)}
    numbers = {record["token"]: number for number, record in enumerate(guests, start=1)}
    staff = {record["token"] for record in guests if record.get("staff") is True}
    pages = {token: f"{token}/index.html" for token in numbers}
    staff_pages = {pages[token] for token in staff}
    for name, text in files.items():
        lowered = text.lower()
        if "{token}" in text:
            problems.append(f"{name}: '{{token}}' is left")
        for token, number in numbers.items():
            if token.lower() in lowered:
                problems.append(f"{name}: the staff token" if token in staff else f"{name}: the token of guest #{number}")
        for word, owners in record_names(guests).items():
            allowed = {pages[guests[owner - 1]["token"]] for owner in owners} | staff_pages
            if name not in allowed and support.occurs(word, text):
                problems.append(f"{name}: the name {word!r}")
        if name not in staff_pages:
            problems += [f"{name}: the label {word!r}" for word in sorted(labels(menu)) if support.occurs(word, text)]
    return problems


class OutputPrivacyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="menu-privacy-test-")
        cls.addClassCleanup(temporary.cleanup)
        cls.tmp = Path(temporary.name).resolve()
        cls.built = {}
        for index, (name, (menu, guests)) in enumerate(data_sets().items()):
            data = fixtures.write_data(cls.tmp / f"data-{index}", menu, guests)
            for base in ("/", "/menu"):
                out = cls.tmp / f"out-{index}{base.replace('/', '-')}"
                result = support.run_main("build", "--data", data, "--out", out, "--base-path", base)
                if result.returncode != 0:
                    raise AssertionError(result.stderr)
                cls.built[name, base] = (out, menu, guests)

    def test_the_finished_pages_show_what_they_may(self):
        for (name, base), (out, menu, guests) in self.built.items():
            with self.subTest(data=name, base=base):
                self.assertEqual(privacy_problems(out, menu, guests), [])

    def test_a_token_is_only_the_name_of_the_directory_of_its_page(self):
        for (name, base), (out, _menu, guests) in self.built.items():
            with self.subTest(data=name, base=base):
                self.assertEqual(
                    sorted(path.name for path in out.iterdir() if path.name != "assets"),
                    sorted(fixtures.tokens(guests)),
                )

    def test_the_names_are_not_part_of_the_shared_texts(self):
        # otherwise a name on a page would prove nothing
        for (name, _base), (out, menu, guests) in self.built.items():
            with self.subTest(data=name):
                shared = json.dumps(menu, ensure_ascii=False)
                for word in record_names(guests):
                    self.assertFalse(support.occurs(word, shared), word)

    def test_the_check_finds_what_leaks(self):
        out, menu, guests = self.built["fixture reserved19", "/menu"]
        copy = self.tmp / "tampered"
        shutil.copytree(out, copy)
        self.addCleanup(shutil.rmtree, copy)
        first, second = guests[0], guests[1]
        staff = next(record["token"] for record in guests if record.get("staff") is True)
        page = copy / first["token"] / "index.html"
        text = page.read_text(encoding="utf-8")
        leak = f"<p>{second['name']} {staff} {first['token']}</p></main>"
        page.write_text(text.replace("</main>", leak, 1), encoding="utf-8")
        other = copy / second["token"] / "index.html"
        text = other.read_text(encoding="utf-8")
        other.write_text(text.replace("</main>", f"<p>{first['token'].upper()}</p></main>", 1), encoding="utf-8")
        with open(copy / "assets" / "app.css", "a", encoding="utf-8") as handle:
            handle.write(f"/* {first['token'].upper()} no nuts */\n")
        problems = privacy_problems(copy, menu, guests)
        for line in (
            f"{first['token']}/index.html: the name {second['name']!r}",
            f"{first['token']}/index.html: the staff token",
            # its own token is a leak as well
            f"{first['token']}/index.html: the token of guest #1",
            f"{second['token']}/index.html: the token of guest #1",
            "assets/app.css: the token of guest #1",
            "assets/app.css: the label 'no nuts'",
        ):
            self.assertIn(line, problems)
        # the untouched pages hold none
        self.assertFalse([line for line in problems if not line.startswith(
            (f"{first['token']}/", f"{second['token']}/", "assets/"))], problems)


if __name__ == "__main__":
    unittest.main()
