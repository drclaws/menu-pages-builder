"""Checks of the CI workflow text (no YAML parser required); the check of
the built pages also runs on builds of the examples."""

import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"

ALLOWED_ACTIONS = {"actions/checkout", "actions/setup-python"}
ALLOWED_EXPRESSIONS = re.compile(
    r"^(matrix\.[\w-]+|github\.ref|github\.workflow|github\.ref != 'refs/heads/main')$")

#: The extensions of media files that must never be tracked.
MEDIA_PATTERN = r"'\.(png|jpe?g|webp|gif|avif|mp4|mov|webm|ico|svg)$'"

HYGIENE = "Repository hygiene (no tracked media, no tracked build output)"
NO_CYRILLIC = "No Cyrillic in tracked files"
UNIT_TESTS = "Unit tests"
BUILD_MAIN = "Validate and build the main example set"
BUILD_PLAIN = "Validate and build the set without a table"
BUILD_BASE_PATH = "Build the main example set under a base path"
CHECK_PAGES = "Check the built pages"
REPRODUCIBLE = "Reproducible build"
CLEAN_TREE = "Working tree stays clean"

#: The steps that build the examples and check the output, in their order.
BUILD_STEPS = [BUILD_MAIN, BUILD_PLAIN, BUILD_BASE_PATH, CHECK_PAGES, REPRODUCIBLE]

#: The steps, in their order.
STEP_NAMES = [
    "Check out the repository",
    "Set up Python ${{ matrix.python }}",
    HYGIENE,
    NO_CYRILLIC,
    UNIT_TESTS,
    *BUILD_STEPS,
    CLEAN_TREE,
]

#: The commands of the build steps (comments and `set -euo pipefail` aside).
BUILD_COMMANDS = {
    BUILD_MAIN: [
        "python build.py validate",
        'python build.py build --out "$RUNNER_TEMP/dist"',
    ],
    BUILD_PLAIN: [
        "python build.py validate --data examples/data-plain",
        'python build.py build --data examples/data-plain --out "$RUNNER_TEMP/dist-plain"',
    ],
    BUILD_BASE_PATH: [
        'python build.py build --base-path /menu --out "$RUNNER_TEMP/site/menu"',
    ],
}

#: (data directory, output directory) of every build the check reads.
CHECKED_BUILDS = [
    ("examples/data", "$RUNNER_TEMP/dist"),
    ("examples/data-plain", "$RUNNER_TEMP/dist-plain"),
    ("examples/data", "$RUNNER_TEMP/site/menu"),
]

#: A Cyrillic letter, made from its code point: this file stays free of them too.
CYRILLIC_LETTER = chr(0x436)


def strip_comments(text):
    """Drop whole-line comments and trailing ``# ...`` comments."""
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(re.sub(r"\s+#\s.*$", "", line))
    return "\n".join(lines) + "\n"


def run_blocks(text):
    """Return the bodies of all ``run: |`` blocks."""
    blocks = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[index])
        index += 1
        if not match:
            continue
        indent = len(match.group(1))
        body = [match.group(2)]
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
            index += 1
        blocks.append("\n".join(body))
    return blocks


def outside_run_blocks(text):
    """Return the text without the values of the ``run:`` keys (the keys stay)."""
    kept = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)(?:-\s+)?run:", lines[index])
        index += 1
        if not match:
            kept.append(lines[index - 1])
            continue
        kept.append(match.group(0))
        indent = len(match.group(1))
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            index += 1
    return "\n".join(kept) + "\n"


def mapping_bodies(text, key, indent=None):
    """Return the non-blank body lines of every ``key:`` with nothing after the colon.

    The body is every following line indented deeper than the key; blank lines
    do not end it, as in YAML.  `indent` limits the search to keys indented by
    exactly that many spaces (0: top-level keys).
    """
    bodies = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"^( *){re.escape(key)}:\s*$", line)
        if not match or (indent is not None and len(match.group(1)) != indent):
            continue
        body = []
        for following in lines[index + 1:]:
            if not following.strip():
                continue
            if len(following) - len(following.lstrip()) <= len(match.group(1)):
                break
            body.append(following)
        bodies.append(body)
    return bodies


def steps(text):
    """Return the items of every ``steps:`` block, each as its non-blank lines."""
    items = []
    for body in mapping_bodies(text, "steps"):
        item_indent = len(body[0]) - len(body[0].lstrip()) if body else 0
        for line in body:
            if len(line) - len(line.lstrip()) <= item_indent or not items:
                items.append([line])
            else:
                items[-1].append(line)
    return items


def step_names(text):
    """The values of the ``- name:`` lines of the steps, in their order."""
    return re.findall(r"(?m)^\s*-\s+name:\s*(.*?)\s*$", text)


def named_runs(text):
    """{step name: body of its ``run:`` command}; a command belongs to the name before it.

    Only a ``run:`` with a value is a command (``defaults: run:`` is a mapping).
    """
    runs = {}
    name = None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        named = re.match(r"^\s*-\s+name:\s*(.*?)\s*$", line)
        if named:
            name = named.group(1)
        elif re.match(r"^\s*(?:-\s+)?run:\s*\S", line):
            runs[name] = run_blocks("\n".join(lines[index:]))[0]
    return runs


def inline_python(block):
    """The programs of the ``python -c '...'`` commands of a ``run: |`` block.

    The block is dedented as YAML does; a program runs from the line after
    ``python -c '`` up to a line that is a lone ``'``.
    """
    script = textwrap.dedent(block.partition("\n")[2])
    return re.findall(r"(?ms)python -c '\n(.*?)^'$", script)


def heredoc_python(block):
    """The programs of the ``python - ... <<'PY'`` commands of a ``run: |``
    block, dedented as YAML does, with the shell words before ``<<``."""
    script = textwrap.dedent(block.partition("\n")[2]).replace("\\\n", " ")
    return re.findall(r"(?ms)^python - (.*?) <<'PY'\n(.*?)^PY$", script)


def commands(block):
    """The command lines of a ``run: |`` block without comments and the
    ``set -euo pipefail`` that every block starts with."""
    lines = [line.strip() for line in textwrap.dedent(block.partition("\n")[2]).splitlines()]
    return [line for line in lines if line and not line.startswith("#") and line != "set -euo pipefail"]


class CiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CI.read_text(encoding="utf-8")
        cls.text = strip_comments(cls.raw)
        cls.runs = run_blocks(cls.raw)
        cls.steps = steps(cls.text)
        cls.named = named_runs(cls.raw)

    def test_single_workflow_file(self):
        names = sorted(path.name for path in WORKFLOWS.iterdir()
                       if path.suffix in (".yml", ".yaml"))
        self.assertEqual(names, ["ci.yml"])

    def test_actions_are_allowed_and_pinned_by_full_sha(self):
        uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", self.raw, flags=re.M)
        self.assertTrue(uses)
        for reference, rest in uses:
            action, _, revision = reference.partition("@")
            self.assertIn(action, ALLOWED_ACTIONS)
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
            self.assertRegex(rest, r"^\s+#\s+v\d+\.\d+\.\d+\s*$")
        # every `uses:` is one of the lines checked above (none hides in a flow mapping)
        self.assertEqual(len(re.findall(r"\buses\s*:", self.text)), len(uses))

    def test_every_checkout_does_not_persist_credentials(self):
        checkouts = [step for step in self.steps
                     if any(re.match(r"^\s*(?:-\s+)?uses:\s*actions/checkout@", line)
                            for line in step)]
        self.assertTrue(checkouts)
        self.assertEqual(len(checkouts), len(re.findall(r"actions/checkout@", self.text)))
        for step in checkouts:
            keys = [line.strip() for line in step]
            self.assertIn("with:", keys)
            self.assertIn("persist-credentials: false", keys)
        self.assertEqual(set(re.findall(r"persist-credentials:\s*(\S*)", self.text)), {"false"})

    def test_triggers(self):
        bodies = mapping_bodies(self.text, "on", indent=0)
        self.assertEqual(len(bodies), 1)
        # the whole block: a trigger added after these is caught as well
        self.assertEqual([line.strip() for line in bodies[0]],
                         ["push:", "pull_request:", "workflow_dispatch:"])
        self.assertRegex(self.text, r"(?m)^on:\n  push:\n  pull_request:\n  workflow_dispatch:\n\n")
        self.assertNotIn("pull_request_target", self.raw)
        self.assertNotIn("workflow_run", self.raw)

    def test_read_only_permissions(self):
        self.assertEqual(len(re.findall(r"(?m)^[ \t]*permissions:", self.text)), 1)
        bodies = mapping_bodies(self.text, "permissions", indent=0)
        self.assertEqual(len(bodies), 1)
        self.assertEqual([line.strip() for line in bodies[0]], ["contents: read"])
        self.assertNotRegex(self.text, r":\s*write\b")
        self.assertNotIn("write-all", self.raw)

    def test_workflow_is_written_in_block_style(self):
        """No flow mappings: every key is on a line of its own, where the checks see it."""
        structure = re.sub(r"\$\{\{.*?\}\}", "", outside_run_blocks(self.text))
        self.assertNotIn("{", structure)
        self.assertNotIn("}", structure)
        self.assertEqual(re.findall(r"(?m)^\s+steps:(.*)$", self.text), [""])
        self.assertGreaterEqual(len(self.steps), 5)
        for step in self.steps:
            self.assertRegex(step[0], r"^\s*-\s+[A-Za-z-]+:(\s|$)")

    def test_steps_cannot_be_skipped_or_fail_silently(self):
        self.assertNotIn("continue-on-error", self.raw)
        self.assertNotRegex(self.text, r"(?m)^\s*(?:-\s+)?[\"']?if[\"']?\s*:")

    def test_no_secrets_deploy_or_uploads(self):
        self.assertNotIn("secrets.", self.raw)
        self.assertNotRegex(self.raw, r"(?i)github_token|upload-artifact|deploy-pages")

    def test_expressions_are_limited_to_safe_contexts(self):
        expressions = re.findall(r"\$\{\{\s*(.*?)\s*\}\}", self.raw)
        self.assertTrue(expressions)
        for expression in expressions:
            self.assertRegex(expression, ALLOWED_EXPRESSIONS)
        self.assertNotIn("github.event.", self.raw)

    def test_run_blocks_contain_no_expressions(self):
        self.assertGreaterEqual(len(self.runs), 3)
        for block in self.runs:
            self.assertNotIn("${{", block)
            self.assertNotIn("github.event.", block)

    def test_matrix_and_runner(self):
        matrix = re.search(r"(?m)^\s+python:\s*\[(.*)\]\s*$", self.text)
        self.assertIsNotNone(matrix)
        versions = [item.strip() for item in matrix.group(1).split(",")]
        self.assertEqual(versions, ['"3.10"', '"3.11"', '"3.12"', '"3.13"'])
        # the list is the whole matrix: nothing added or taken away
        bodies = mapping_bodies(self.text, "matrix")
        self.assertEqual(len(bodies), 1)
        self.assertEqual([line.strip() for line in bodies[0]],
                         ['python: ["3.10", "3.11", "3.12", "3.13"]'])
        self.assertNotIn("include:", self.text)
        self.assertNotIn("exclude:", self.text)
        self.assertRegex(self.text, r"(?m)^\s+fail-fast:\s*false$")
        self.assertRegex(self.text, r"(?m)^\s+runs-on:\s*ubuntu-\d+\.\d+$")
        self.assertRegex(self.text, r"(?m)^\s+timeout-minutes:\s*\d+$")

    def test_concurrency_cancels_stale_runs(self):
        self.assertRegex(
            self.text,
            r"(?m)^concurrency:\n  group: .*github\.ref.*\n"
            r"  cancel-in-progress: \$\{\{ github\.ref != 'refs/heads/main' \}\}$",
        )

    def test_the_steps_and_their_order(self):
        self.assertEqual(step_names(self.raw), STEP_NAMES)
        self.assertEqual(list(self.named), [HYGIENE, NO_CYRILLIC, UNIT_TESTS, *BUILD_STEPS, CLEAN_TREE])
        # every command is one of these (the other `run:` is the mapping of `defaults`)
        commands = [block for block in self.runs if block.startswith("|")]
        self.assertEqual(commands, list(self.named.values()))
        self.assertEqual(len(commands), len(self.runs) - 1)

    def test_hygiene_checks_every_tracked_file_for_media(self):
        hygiene = [block for block in self.runs if "ls-files" in block]
        self.assertEqual(len(hygiene), 2)
        block = self.named[HYGIENE]
        self.assertIn(block, hygiene)
        listings = re.findall(r"git\b.*?\bls-files\b[^|)]*", block)
        self.assertGreaterEqual(len(listings), 2)
        for listing in listings:
            self.assertRegex(listing, r"^git -c core\.quotePath=false ls-files -z\b")
        self.assertIn("must not contain line breaks or carriage returns", block)
        # the whole tree: no path given to the listing, no directory filtered out
        self.assertIn(f'media="$(tracked | grep -aEi {MEDIA_PATTERN} || true)"', block)
        self.assertNotRegex(block, r"grep\s+-[A-Za-z]*v")
        self.assertIn('output="$(tracked dist)"', block)
        self.assertEqual(block.count("exit 1"), 3)

    def test_cyrillic_check_lists_every_tracked_file(self):
        block = self.named[NO_CYRILLIC]
        self.assertIn("set -euo pipefail", block)
        listings = re.findall(r"git\b.*?\bls-files\b[^|]*\|", block)
        # the whole listing: no path, no filter
        self.assertEqual(listings, ["git ls-files -z |"])
        self.assertIn("git ls-files -z | python -c '", block)
        # Python, not `git grep -P` (PCRE is not in every build of git)
        self.assertNotRegex(block, r"\bgrep\b")
        self.assertEqual(len(inline_python(block)), 1)

    def test_cyrillic_check_program(self):
        program = inline_python(self.named[NO_CYRILLIC])[0]
        # the whole Cyrillic block of Unicode, by code point
        self.assertIn("0x400 <= ord(char) <= 0x4FF", program)
        self.assertTrue(program.isascii())
        self.assertNotIn("'", program)  # the program is one single-quoted shell word
        # one report at the end, on stderr; what it holds is checked below
        self.assertEqual(len(re.findall(r"\bprint\(", program)), 1)
        self.assertIn("file=sys.stderr", program)
        self.assertIn("sys.exit(1)", program)

    def test_cyrillic_check_prints_the_names_and_line_numbers_only(self):
        program = inline_python(self.named[NO_CYRILLIC])[0]
        with tempfile.TemporaryDirectory(prefix="menu-ci-test-") as temporary:
            work = Path(temporary)
            (work / "clean.txt").write_text("plain\ntext\n", encoding="utf-8")
            (work / "mixed.txt").write_text(
                f"first\nsecond {CYRILLIC_LETTER}\nthird\n{CYRILLIC_LETTER}\n", encoding="utf-8")
            (work / f"name-{CYRILLIC_LETTER}.txt").write_text("plain\n", encoding="utf-8")
            # Cyrillic in another encoding: no Cyrillic letter once read as UTF-8
            (work / "legacy.txt").write_bytes(f"first\n{CYRILLIC_LETTER}\n".encode("cp1251"))

            def check(*names):
                listing = b"".join((name if isinstance(name, bytes) else name.encode("utf-8"))
                                   + b"\0" for name in names)
                environ = dict(os.environ, PYTHONIOENCODING="utf-8")
                return subprocess.run([sys.executable, "-c", program], cwd=str(work),
                                      env=environ, input=listing, capture_output=True)

            clean = check("clean.txt")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(clean.stdout + clean.stderr, b"")

            found = check("clean.txt", "mixed.txt", f"name-{CYRILLIC_LETTER}.txt",
                          "legacy.txt", b"name-\xe6.txt")
            self.assertEqual(found.returncode, 1)
            self.assertEqual(found.stdout, b"")
            self.assertEqual(found.stderr.decode("utf-8").splitlines(), [
                "Tracked files must be UTF-8 without Cyrillic:",
                "mixed.txt:2",
                "mixed.txt:4",
                f"name-{CYRILLIC_LETTER}.txt: in the file name",
                "legacy.txt: not UTF-8",
                "name-\N{REPLACEMENT CHARACTER}.txt: not UTF-8",
            ])

            legacy = check("clean.txt", "legacy.txt")
            self.assertEqual(legacy.returncode, 1)
            self.assertEqual(legacy.stderr.decode("utf-8").splitlines()[1:], ["legacy.txt: not UTF-8"])

    def test_unit_tests_discover_the_tests_package(self):
        tests = [block for block in self.runs if "unittest" in block]
        self.assertEqual(tests, [self.named[UNIT_TESTS]])
        commands = [line.strip() for line in tests[0].splitlines()[1:] if line.strip()]
        self.assertEqual(commands, ["set -euo pipefail", "python -m unittest discover -s tests -t ."])

    def test_working_tree_stays_clean_at_the_end(self):
        last = self.runs[-1]
        self.assertEqual(last, self.named[CLEAN_TREE])
        self.assertIn('status="$(git status --porcelain)"', last)
        self.assertIn("exit 1", last)

    def test_no_browser_or_media_tools(self):
        for name in ("chrome", "chromium", "ffmpeg", "apt-get"):
            self.assertNotIn(name, self.raw.lower())

    def test_every_build_step_fails_on_the_first_error(self):
        for name in BUILD_STEPS:
            with self.subTest(step=name):
                self.assertEqual(self.named[name].splitlines()[1].strip(), "set -euo pipefail")

    def test_the_examples_are_validated_and_built(self):
        for name, expected in BUILD_COMMANDS.items():
            with self.subTest(step=name):
                self.assertEqual(commands(self.named[name]), expected)
        # the main set is built once at the top of a site and once under the
        # base path of a real site; every build writes to the runner's directory
        builds = [line for block in self.named.values() for line in commands(block)
                  if line.startswith("python build.py build")]
        self.assertTrue(all("--out \"$RUNNER_TEMP/" in line for line in builds), builds)

    def test_the_check_reads_every_build(self):
        programs = heredoc_python(self.named[CHECK_PAGES])
        self.assertEqual(len(programs), 1)
        words, program = programs[0]
        pairs = re.findall(r'(\S+) ("\$RUNNER_TEMP/[^"]+")', words)
        self.assertEqual([(data, out.strip('"')) for data, out in pairs], CHECKED_BUILDS)
        self.assertTrue(program.isascii())

    def test_the_check_of_the_pages_finds_what_is_wrong(self):
        # the builds the check reads, made here as the steps before it make them
        from tests import support

        _words, program = heredoc_python(self.named[CHECK_PAGES])[0]
        with tempfile.TemporaryDirectory(prefix="menu-ci-test-") as temporary:
            work = Path(temporary)
            arguments = []
            for data, out in CHECKED_BUILDS:
                target = work / out.replace("$RUNNER_TEMP/", "")
                extra = ["--base-path", "/menu"] if "/site/" in out else []
                if not target.exists():
                    result = support.run_main("build", "--data", ROOT / data, "--out", target, *extra)
                    self.assertEqual(result.returncode, 0, result.stderr)
                arguments += [str(ROOT / data), str(target)]

            def check():
                return subprocess.run([sys.executable, "-", *arguments], input=program, capture_output=True,
                                      text=True, encoding="utf-8", cwd=str(work))

            passed = check()
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(len(passed.stdout.splitlines()), 3)
            self.assertTrue(all(line.startswith("OK: ") for line in passed.stdout.splitlines()))
            page = next((work / "dist-plain").glob("*/index.html"))
            token = page.parent.name
            original = page.read_text(encoding="utf-8")
            # the pages that passed above have the links of the line of the sections
            self.assertIn('<a class="section-nav__link" href="#s-seats"', original)

            def with_body(markup):
                return original.replace("</main>", f"{markup}</main>", 1)

            broken = {
                "a style attribute": original.replace("<main ", '<main style="margin: 0" ', 1),
                "a placeholder": with_body("<p>{token}</p>"),
                "a link to another page": with_body('<p><a href="/other/">Other</a></p>'),
                "a link to an id the page does not have": with_body('<p><a href="#nowhere">Nowhere</a></p>'),
                "an empty fragment": with_body('<p><a href="#">Top</a></p>'),
                "a link without href": with_body("<p><a>Top</a></p>"),
                "an area that leads elsewhere": with_body(
                    '<map name="m"><area shape="rect" coords="0,0,1,1" href="/other/" alt=""></map>'),
                "the own token": with_body(f"<p>{token.upper()}</p>"),
            }
            for name, text in broken.items():
                with self.subTest(case=name):
                    page.write_text(text, encoding="utf-8")
                    failed = check()
                    self.assertNotEqual(failed.returncode, 0)
                    printed = (failed.stdout + failed.stderr).lower()
                    self.assertNotIn(token.lower(), printed)
                    for value in ("nowhere", "/other/"):
                        self.assertNotIn(value, printed)
            # a link to a part of the same page: the id of its cover
            for markup in ('<p><a href="#s-cover">Top</a></p>',
                           '<map name="m" id="m"><area shape="rect" coords="0,0,1,1" href="#m" alt=""></map>'):
                with self.subTest(case=markup):
                    self.assertIn(' id="s-cover"', original)
                    page.write_text(with_body(markup), encoding="utf-8")
                    passed = check()
                    self.assertEqual(passed.returncode, 0, passed.stderr)
            page.write_text(original, encoding="utf-8")
            style_sheet = work / "dist-plain" / "assets" / "app.css"
            css = style_sheet.read_text(encoding="utf-8")
            with self.subTest(case="a token in the shared files"):
                style_sheet.write_text(f"{css}/* {token} */\n", encoding="utf-8")
                failed = check()
                self.assertNotEqual(failed.returncode, 0)
                self.assertNotIn(token.lower(), (failed.stdout + failed.stderr).lower())
            style_sheet.write_text(css, encoding="utf-8")
            self.assertEqual(check().returncode, 0)
            (work / "dist-plain" / "assets" / "extra.css").write_text("", encoding="utf-8")
            self.assertNotEqual(check().returncode, 0)

    def test_the_reproducible_build_repeats_the_first_build(self):
        lines = commands(self.named[REPRODUCIBLE])
        first = BUILD_COMMANDS[BUILD_MAIN][1]
        self.assertEqual(lines[0], first.replace('"$RUNNER_TEMP/dist"', '"$RUNNER_TEMP/dist2"'))
        self.assertIn('diff "$RUNNER_TEMP/dist.sha256" "$RUNNER_TEMP/dist2.sha256"', lines)
        self.assertIn('test -s "$RUNNER_TEMP/dist.sha256"', lines)


if __name__ == "__main__":
    unittest.main()
