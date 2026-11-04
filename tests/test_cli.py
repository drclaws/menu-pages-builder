"""Tests of the `build.py` command line (standard library only)."""

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build  # noqa: E402  (imported after sys.path is prepared)
from tests import fixtures  # noqa: E402

SCRIPT = ROOT / "build.py"

if Path(build.__file__).resolve() != SCRIPT:  # pragma: no cover
    raise RuntimeError(f"unexpected build module: {build.__file__}")

COMMANDS = ("build", "validate", "links", "token")

#: The width argparse wraps its messages to, the same in and out of process.
COLUMNS = "80"

#: What `validate` prints for each fixture.
SUMMARIES = {
    "mockup16": "validate: OK - 16 seat(s), 10 guest record(s) + staff, 9 dish(es), 2 set(s), 4 drink(s)\n",
    "reserved19": "validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), 2 set(s), 5 drink(s)\n",
    "plain": "validate: OK - 4 seat(s), 3 guest record(s) + staff, 6 dish(es), 3 set(s), 2 drink(s)\n",
    "parts": "validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), 2 set(s), 5 drink(s)\n",
}
WARNINGS = {
    "mockup16": (
        "warning: menu.json: field 'table.seats' has 2 free seat(s): 12, 13 (shown as free on the staff page; "
        "list a seat that stays free on purpose in 'reservedSeats')\n"
    ),
    "reserved19": "",
    "plain": "",
    "parts": "",
}


def run_main(*args: str, cwd: Path | None = None) -> SimpleNamespace:
    """Run `build.main()` in-process (from the directory `cwd`, if given);
    argparse exits are turned into codes."""
    stdout, stderr = io.StringIO(), io.StringIO()
    previous = os.getcwd()
    with (
        mock.patch.dict(os.environ, {"COLUMNS": COLUMNS}),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            if cwd is not None:
                os.chdir(cwd)
            code = build.main([str(arg) for arg in args])
        except SystemExit as exc:  # argparse: --help and usage errors
            code = exc.code if isinstance(exc.code, int) else 2
        finally:
            os.chdir(previous)
    return SimpleNamespace(returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def subprocess_env() -> dict:
    """A child Python's environment: UTF-8 output, no bytecode files."""
    environ = dict(os.environ)
    environ["COLUMNS"] = COLUMNS
    environ["PYTHONIOENCODING"] = "utf-8"
    environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return environ


def run_script(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run `python build.py ...` as a script from the directory `cwd`."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd),
        env=subprocess_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class CliTest(unittest.TestCase):
    def test_help_exits_with_zero(self):
        result = run_main("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
        for command in COMMANDS:
            self.assertIn(command, result.stdout)
        self.assertEqual(result.stderr, "")

    def test_no_command_prints_usage_and_exits_with_two(self):
        result = run_main()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_build_takes_the_data_the_output_and_the_base_path(self):
        result = run_main("build", "--help")
        self.assertEqual(result.returncode, 0)
        for option in ("--data DIR", "--out DIR", "--base-path PATH"):
            self.assertIn(option, result.stdout)
        self.assertEqual(re.findall(r"(?m)^  (--[\w-]+)", result.stdout), ["--data", "--out", "--base-path"])
        # any other option is a bad command line
        for extra in (("--theme", "dark"), ("--watch",)):
            with self.subTest(extra=extra):
                result = run_main("build", *extra)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn(f"unrecognized arguments: {' '.join(extra)}", result.stderr)

    def test_validate_takes_the_data_directory_only(self):
        result = run_main("validate", "--out", "dist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)
        result = run_main("validate", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--data DIR", result.stdout)

    def test_unknown_command_exits_with_two(self):
        result = run_main("deploy")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_import_has_no_output(self):
        with tempfile.TemporaryDirectory(prefix="menu-build-test-") as temporary:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0, sys.argv[1]); import build", str(ROOT)],
                cwd=temporary,
                env=subprocess_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_script_from_another_directory_behaves_the_same(self):
        with tempfile.TemporaryDirectory(prefix="menu-build-test-") as temporary:
            base = Path(temporary).resolve()
            menu, guests = fixtures.reserved19()
            data = fixtures.write_data(base / "data", menu, guests)
            work = base / "work"
            work.mkdir()
            out = base / "out"
            cases = (
                ("--help",),
                (),
                ("build", "--data", str(base / "nowhere"), "--out", str(out)),
                ("build", "--data", str(data), "--out", str(out)),
                ("validate", "--data", str(data)),
                ("token", "--prefix", "a b"),
                ("links", "--url", "ftp://example.org/menu", "--data", str(data)),
                ("deploy",),
            )
            for args in cases:
                with self.subTest(args=args):
                    expected = run_main(*args, cwd=work)
                    result = run_script(*args, cwd=work)
                    self.assertEqual(result.returncode, expected.returncode)
                    self.assertEqual(result.stdout, expected.stdout)
                    self.assertEqual(result.stderr, expected.stderr)
            # nothing is written to the current directory, nor next to the data
            self.assertEqual(list(work.iterdir()), [])
            self.assertEqual(sorted(path.name for path in data.iterdir()), ["guests.json", "menu.json"])
            self.assertEqual(sorted(path.name for path in base.iterdir()), ["data", "out", "work"])


class TokenTest(unittest.TestCase):
    def check(self, token: str) -> None:
        from menu_tools import _core

        self.assertIsNone(_core.check_token(token))
        self.assertNotIn(token.lower(), _core.RESERVED_TOKENS)

    def test_a_random_token(self):
        tokens = set()
        for _ in range(3):
            result = run_main("token")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertRegex(result.stdout, r"\A[A-Za-z0-9_-]{16,}\n\Z")
            self.check(result.stdout.strip())
            tokens.add(result.stdout)
        self.assertEqual(len(tokens), 3)

    def test_a_readable_token(self):
        for prefix in ("heron", "Crane_2", "a"):
            with self.subTest(prefix=prefix):
                result = run_main("token", "--prefix", prefix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertRegex(result.stdout, rf"\A{prefix}-[a-z0-9]{{4}}\n\Z")
                self.check(result.stdout.strip())

    def test_a_bad_prefix_is_a_usage_error_that_does_not_repeat_it(self):
        for prefix in ("a b", "", "Rosalind's", "Leopold" * 30, "judy/x"):
            with self.subTest(prefix=prefix):
                result = run_main("token", "--prefix", prefix)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("build.py token: error: argument --prefix: the prefix", result.stderr)
                if prefix:
                    self.assertNotIn(prefix, result.stderr)
                for word in ("Rosalind", "Leopold", "judy"):
                    self.assertNotIn(word, result.stderr)

    def test_token_reads_no_data(self):
        result = run_main("token", "--data", "data")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_as_a_script(self):
        with tempfile.TemporaryDirectory(prefix="menu-build-test-") as temporary:
            result = run_script("token", "--prefix", "heron", cwd=Path(temporary))
            self.assertEqual(list(Path(temporary).iterdir()), [])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"\Aheron-[a-z0-9]{4}\n\Z")


class BuildArgumentsTest(unittest.TestCase):
    """`--base-path` is checked before anything is read."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="menu-build-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        # neither exists: a refusal before the data is read is a usage error
        self.args = ("build", "--data", str(self.base / "nowhere"), "--out", str(self.base / "out"))

    def test_each_refused_value_is_a_usage_error_that_does_not_repeat_it(self):
        for value in ("https://leopold.example.org/x", "/bjarne/../x", "rosalind", "/judy path"):
            with self.subTest(value=value):
                result = run_main(*self.args, "--base-path", value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage: build.py build", result.stderr)
                self.assertIn("build.py build: error: argument --base-path: must be a path from the root "
                              "of the site", result.stderr)
                self.assertNotIn(value, result.stderr)
                for word in ("judy", "bjarne", "rosalind", "leopold"):
                    self.assertNotIn(word, result.stderr)
                self.assertFalse((self.base / "out").exists())


class ValidateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="menu-validate-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()

    def validate(self, menu, guests, name: str = "data") -> SimpleNamespace:
        data = fixtures.write_data(self.base / name, menu, guests)
        return run_main("validate", "--data", str(data))

    def assert_no_values(self, text: str, menu, guests) -> None:
        for secret in fixtures.tokens(guests) | fixtures.names(guests, menu):
            self.assertNotIn(secret, text)

    def test_each_fixture_passes(self):
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                result = self.validate(*make(), name=name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, SUMMARIES[name])
                self.assertEqual(result.stderr, WARNINGS[name])

    def test_broken_data_fails_with_messages_without_values(self):
        menu, guests = fixtures.reserved19()
        guests[3]["seats"][0]["number"] = 4
        menu["dishes"]["hummus"]["ingredient"] = "Chickpeas"
        result = self.validate(menu, guests)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "error: menu.json: unknown field 'dishes.hummus.ingredient' (did you mean 'ingredients'?)\n"
            "error: guests.json: guest #4: field 'seats[0].number' refers to the seat 4, already taken by guest #3\n"
            "validate: failed with 2 error(s)\n",
        )
        self.assert_no_values(result.stderr, menu, guests)

    def test_warnings_come_first_and_do_not_fail(self):
        menu, guests = fixtures.reserved19()
        del guests[12]
        result = self.validate(menu, guests)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "validate: OK - 19 seat(s), 12 guest record(s), 8 dish(es), 2 set(s), 5 drink(s)\n",
        )
        self.assertEqual(
            result.stderr.splitlines(),
            [
                "warning: guests.json: has no staff record ('staff': true): no staff page is built",
                "warning: menu.json: field 'sections' has parts for the staff only (sections[2].widgets[1], "
                "sections[4].widgets[1]), but there is no staff record",
            ],
        )

    def test_a_record_of_more_seats_than_colours_fails(self):
        # a guest page tells the record's seats apart by colour alone: three
        # colours, so at most three seats; the message holds no name
        menu, guests = fixtures.plain()
        guests[:3] = [{"token": "lynx-5qd8", "name": "Lev",
                       "seats": [{"number": 1}, {"number": 2, "plusOne": True}, {"number": 3, "plusOne": True},
                                 {"number": 4, "plusOne": True}]}]
        result = self.validate(menu, guests)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr.splitlines()[-2:],
            ["error: guests.json: guest #1: field 'seats' lists 4 seats, at most 3 are allowed: a guest page "
             "marks each of the record's seats in a colour of its own (split the record in two)",
             "validate: failed with 1 error(s)"],
        )
        self.assertNotIn("Lev", result.stderr)
        guests[0]["seats"].pop()
        result = self.validate(menu, guests)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_missing_directory_or_file(self):
        missing = self.base / "nowhere"
        result = run_main("validate", "--data", str(missing))
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("error: data directory not found: "), result.stderr)
        data = fixtures.write_data(self.base / "data", *fixtures.plain())
        (data / "guests.json").unlink()
        result = run_main("validate", "--data", str(data))
        self.assertEqual(result.returncode, 1)
        lines = result.stderr.splitlines()
        self.assertTrue(lines[0].startswith("error: ") and lines[0].endswith("guests.json: file not found"), lines)
        self.assertEqual(lines[1:], ["validate: failed with 1 error(s)"])

    def test_the_default_data_directory_is_next_to_the_script(self):
        # the main example set, whatever the current directory
        expected = "validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), 2 set(s), 5 drink(s)\n"
        for cwd in (None, self.base):
            with self.subTest(cwd=cwd):
                result = run_main("validate", cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.stderr, "")
        result = run_script("validate", cwd=self.base)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, ""))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_a_token_in_a_path_is_hidden(self):
        # the data lies in a directory named after a token, and a message names
        # a file in it: the token is masked
        menu, guests = fixtures.reserved19()
        token = guests[0]["token"]
        data = fixtures.write_data(self.base / token, menu, guests)
        (data / "menu.json").write_text('{"schemaVersion": 1,', encoding="utf-8")
        result = run_main("validate", "--data", str(data))
        self.assertEqual(result.returncode, 1)
        self.assertIn("menu.json: invalid JSON", result.stderr)
        self.assertNotIn(token, result.stderr)
        self.assertIn("…", result.stderr)

    def test_a_key_repeated_in_guests_json_is_not_named(self):
        menu, guests = fixtures.reserved19()
        data = fixtures.write_data(self.base / "data", menu, guests)
        text = (data / "guests.json").read_text(encoding="utf-8")
        text = text.replace('"name": "Boris",', '"name": "Boris", "Boris": 1, "Boris": 2,', 1)
        (data / "guests.json").write_text(text, encoding="utf-8")
        result = run_main("validate", "--data", str(data))
        self.assertEqual(result.returncode, 1)
        lines = result.stderr.splitlines()
        self.assertTrue(
            lines[0].endswith("guests.json: duplicate key <unknown key> in '[2]' (JSON keeps only the last one; merge or rename them)"),
            lines,
        )
        self.assert_no_values(result.stderr, menu, guests)

    def test_an_internal_error_quotes_no_data(self):
        menu, guests = fixtures.reserved19()
        data = fixtures.write_data(self.base / "data", menu, guests)
        with mock.patch.object(build, "summary", side_effect=KeyError("Olga")), mock.patch.dict(os.environ, {"BUILD_DEBUG": ""}):
            result = run_main("validate", "--data", str(data))
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r"^error: internal error: KeyError at \S+:\d+ \(set BUILD_DEBUG=1 for the traceback\)\n")
        self.assertTrue(result.stderr.endswith("validate: failed\n"))
        self.assertNotIn("Olga", result.stderr)

    def test_load_data_returns_the_checked_data_and_the_trees(self):
        from menu_tools import _core

        data = fixtures.write_data(self.base / "data", *fixtures.reserved19())
        loaded = build.load_data(data, _core.Report())
        self.assertEqual(loaded.index.total, 19)
        self.assertEqual(len(loaded.trees.guests), 12)
        self.assertEqual(loaded.trees.staff.number, 13)
        self.assertEqual(loaded.menu, fixtures.reserved19()[0])


if __name__ == "__main__":
    unittest.main()
