"""Helpers shared by the build tests (standard library only)."""

import contextlib
import hashlib
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

SCRIPT = ROOT / "build.py"
if Path(build.__file__).resolve() != SCRIPT:  # pragma: no cover
    raise RuntimeError(f"unexpected build module: {build.__file__}")

#: Variables a command reads from the environment: the tests behave the same
#: on a developer machine and in CI.
COMMAND_VARIABLES = ("BUILD_DEBUG", "CI", "GITHUB_ACTIONS")


def environment(env: dict | None = None) -> dict:
    """A command's environment: without `COMMAND_VARIABLES`, with `env`."""
    environ = {key: value for key, value in os.environ.items() if key not in COMMAND_VARIABLES}
    environ.update({"COLUMNS": "80", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    environ.update(env or {})
    return environ


def run_script(*args: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run `python build.py ...` as a script from the directory `cwd`."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=str(cwd),
        env=environment(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_main(*args: str, env: dict | None = None) -> SimpleNamespace:
    """Run `build.main()` in-process; argparse exits are turned into codes."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, environment(env), clear=True),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            code = build.main([str(arg) for arg in args])
        except SystemExit as exc:  # argparse: --help and usage errors
            code = exc.code if isinstance(exc.code, int) else 2
    return SimpleNamespace(returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def tree_files(root: Path) -> list[str]:
    """Every file below `root` as sorted relative '/' paths; an empty
    directory is listed with a trailing '/'."""
    root = Path(root)
    found = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir() and not path.is_symlink():
            if not any(path.iterdir()):
                found.append(relative + "/")
        else:
            found.append(relative)
    return sorted(found)


def tree_digest(root: Path) -> dict[str, str]:
    """Relative path -> SHA-256 of the contents, for every file below `root`."""
    return {
        name: hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()
        for name in tree_files(root)
        if not name.endswith("/")
    }


def occurs(word: str, text: str) -> bool:
    """`word` as a whole word of `text` (not inside a longer word, in any
    script: "Ana" does not occur in "Anađelka")."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


class TempDirTestCase(unittest.TestCase):
    """Every test gets its own temporary directory (inside `TMPDIR`)."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="menu-build-test-")
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name).resolve()

    def assertNoPrivateData(self, text: str, tokens=(), names=()) -> None:
        """No token (in any letter case), no name (as a word) and no traceback."""
        for token in tokens:
            self.assertNotIn(token.lower(), text.lower(), "a token leaked into the output")
        for name in names:
            self.assertFalse(occurs(name, text), "a name leaked into the output")
        self.assertNotIn("Traceback", text)
