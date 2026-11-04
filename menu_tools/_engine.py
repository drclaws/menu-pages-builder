"""The engine of the build: templates, the report, the output and its checks.

- `parse_template(source).render(context)` renders a template;
  `load_template` reads the page template with the fragments next to it
  (`load_fragments`), and `strip_html_comments` drops the notes of a
  template from a rendered page.
- `Report` collects the errors and warnings of a command and hides the
  tokens it has seen (`redact`); `BuildError`, `TemplateError` and
  `ValidationError` are the expected failures.  `read_json` reads a JSON
  document and reports its problems without quoting the data.
- `check_output(out_dir, pages)` checks the finished output: nothing but the
  expected files, no external resources, no inline scripts, every local link
  resolves inside the output, no file above the hosting size limit;
  `check_html`, `check_stylesheet` and `check_svg` check one document.
- `check_out_dir` refuses an output directory whose replacement would destroy
  anything; `_StagedOutput` assembles the output next to it and swaps it in
  only when every check has passed; `write_pages` and `copy_assets` fill it.
- `base_path_argument`, `token_prefix` and `parse_published_url` convert
  arguments of the command line; `running_in_ci` tells an automated run.

Importing this module has no side effects.  Only the Python 3 standard
library is used (Python >= 3.10).

Exit codes: 0 - success, 1 - data/build error, 2 - bad command line.
"""

from __future__ import annotations

import argparse
import bisect
import html
import json
import os
import posixpath
import re
import secrets
import shutil
import stat
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, NamedTuple, Sequence
from urllib.parse import unquote, urlsplit

from menu_tools import _values as data_tools
from menu_tools._values import check_token_prefix, format_size, json_type

# --------------------------------------------------------------------------
# Layout constants
# --------------------------------------------------------------------------

ASSETS_DIRNAME = "assets"

#: Output layout: `<out>/<token>/index.html` for every page and
#: `<out>/assets/` for everything the pages share; nothing else.
PAGE_FILE = "index.html"

#: `build --base-path`: the path from the root of the site under which the
#: contents of `--out` are published.  Every URL of the output starts with it:
#: `<base path>/assets/…`, and the page of a guest is `<base path>/<token>/`.
DEFAULT_BASE_PATH = "/"
MAX_BASE_PATH_LENGTH = 200
#: `/` or `/seg[/seg…]` with an optional trailing `/`.
_BASE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9_-]+)*/?")

#: Files created by the operating system; ignored when `--out` is inspected.
OS_JUNK_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})

#: Hosting limit for a single file.
MAX_FILE_BYTES = 25 * 1024 * 1024
#: The types of the files the build writes; a message about a path shows its
#: extension only when it is one of them.
SHOWN_EXTENSIONS = frozenset({".html", ".css", ".js", ".svg"})
#: Never published, wherever they turn up in the output.
FORBIDDEN_OUTPUT_EXTENSIONS = frozenset({".json", ".map", ".py", ".md"})

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class BuildError(Exception):
    """Expected failure: reported as a plain message, never as a traceback."""


class TemplateError(BuildError):
    """Malformed template or a value that cannot be rendered.

    An error inside a fragment names the fragment file and line, followed by
    the places it was included from (`chain`, innermost first).
    """

    def __init__(
        self,
        message: str,
        line: int | None = None,
        name: str = "template",
        chain: Sequence[str] = (),
    ):
        self.reason = message
        self.line = line
        self.name = name
        self.chain = tuple(chain)
        where = f"{name} line {line}" if line else name
        text = f"{where}: {message}"
        if self.chain:
            text += f" (included from {' <- '.join(self.chain)})"
        super().__init__(text)

    def via(self, name: str, line: int) -> "TemplateError":
        """The same error, seen from the include at `name` line `line`."""
        return TemplateError(
            self.reason, self.line, self.name, self.chain + (f"{name} line {line}",)
        )


class ValidationError(BuildError):
    """One or more problems in the input data (all of them are collected)."""

    def __init__(self, errors: Iterable[str], warnings: Iterable[str] = ()):
        self.errors = list(errors)
        self.warnings = list(warnings)
        super().__init__("; ".join(self.errors))


class Report:
    """Collects validation errors and warnings instead of failing fast.

    `on_warn` lets the caller show warnings as soon as they appear (the CLI
    prints them to stderr); errors are always reported together at the end.

    The report also remembers the tokens of the records as soon as
    `guests.json` is read (`remember_tokens`), so that whatever prints the
    messages of a command can hide them (`redact`): a path that a message
    shows may lead through the directory of a page.
    """

    def __init__(self, on_warn: Callable[[str], None] | None = None) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        #: The valid tokens of the records, in lower case.
        self.tokens: frozenset[str] = frozenset()
        self._on_warn = on_warn

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        if self._on_warn is not None:
            self._on_warn(message)

    def remember_tokens(self, records: Any) -> None:
        """Remember the tokens of `records` (the parsed `guests.json`,
        whatever its shape): every value that is a valid token."""
        if not isinstance(records, list):
            return
        found = {
            item["token"].lower()
            for item in records
            if isinstance(item, dict) and data_tools.check_token(item.get("token")) is None
        }
        self.tokens = self.tokens | found

    def redact(self, text: Any) -> str:
        """`text` with the tokens hidden (`redact_tokens`)."""
        return redact_tokens(text, self.tokens)

    def raise_if_failed(self) -> None:
        if self.errors:
            raise ValidationError(self.errors, self.warnings)


# Sentinel for "no such field" (distinct from a field whose value is null).
class _MissingType:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"

    def __bool__(self) -> bool:
        return False


MISSING = _MissingType()


# --------------------------------------------------------------------------
# Template engine
# --------------------------------------------------------------------------

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
#: `field`, `event.title`, `.field` (field of the current item), `.` (the item)
_PATH_RE = re.compile(rf"(?:\.|\.?{_NAME}(?:\.{_NAME})*)\Z")
_PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")
_BRACES_RE = re.compile(r"\{\{|\}\}")
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
#: Words that open a directive: `<!-- if:… -->`, `<!-- endif -->` and so on.
_DIRECTIVE_WORDS = r"(?:if|each|with|include)\s*:|(?:endif|endeach|endwith)\b"
#: A comment that is meant to be a directive (anything else stays literal text).
_DIRECTIVE_LIKE_RE = re.compile(_DIRECTIVE_WORDS, re.IGNORECASE)
_IF_RE = re.compile(r"if\s*:\s*(!?)\s*(\S*)\Z")
_EACH_RE = re.compile(r"each\s*:\s*(\S*)\Z")
_WITH_RE = re.compile(r"with\s*:\s*(\S*)\Z")
#: Template syntax that must not survive rendering.
_LEFTOVER_RE = re.compile(rf"\{{\{{|\}}\}}|<!--\s*(?:{_DIRECTIVE_WORDS})", re.IGNORECASE)

#: Fragments of the template live in this directory next to `template.html`.
#: They are code: read once before rendering and never copied to the output.
FRAGMENTS_DIRNAME = "fragments"
FRAGMENT_SUFFIX = ".html"
#: One part of a fragment name: `widgets/text` is the file `widgets/text.html`.
#: A value that chooses a fragment must be exactly one such part.
_SEGMENT = r"[a-z][a-z0-9-]{0,39}"
_SEGMENT_RE = re.compile(rf"{_SEGMENT}\Z")
_FRAGMENT_NAME_RE = re.compile(rf"{_SEGMENT}(?:/{_SEGMENT})*\Z")
#: `include:dir/name` (a fixed fragment) or `include:dir/{{.field}}` (the
#: value of the field names a fragment in `dir/`).
_INCLUDE_RE = re.compile(
    rf"include\s*:\s*(?:({_SEGMENT}(?:/{_SEGMENT})*)"
    rf"|((?:{_SEGMENT}/)+)\{{\{{\s*(\S+?)\s*\}}\}})\Z"
)
#: Fragments nested deeper than this are a runaway recursion through the data.
MAX_INCLUDE_DEPTH = 12

_PARAGRAPH_BREAK_RE = re.compile(r"\n(?:[ \t]*\n)+")
_LEADING_BLANK_RE = re.compile(r"\A(?:[ \t]*\n)+")
_TRAILING_BLANK_RE = re.compile(r"(?:\n[ \t]*)+\Z")


class _Var:
    """`{{path}}` inside the template."""

    __slots__ = ("path", "line")

    def __init__(self, path: str, line: int):
        self.path = path
        self.line = line


class _Block:
    """`<!-- if:path -->…<!-- endif -->`, `<!-- each:path -->…<!-- endeach -->`
    or `<!-- with:path -->…<!-- endwith -->`."""

    __slots__ = ("kind", "path", "negate", "line", "children")

    def __init__(self, kind: str, path: str, negate: bool, line: int):
        self.kind = kind  # "if" | "each" | "with"
        self.path = path
        self.negate = negate
        self.line = line
        self.children: list[Any] = []


class _Include:
    """`<!-- include:dir/name -->` or `<!-- include:dir/{{.field}} -->`."""

    __slots__ = ("name", "directory", "path", "line", "in_scope")

    def __init__(self, name: str, directory: str, path: str, line: int, in_scope: bool):
        self.name = name  # a fixed fragment, or "" when the data chooses it
        self.directory = directory  # the data chooses a fragment in this directory
        self.path = path  # ... by the value of this field of the current item
        self.line = line
        #: Inside `each`/`with` of the same file: the item there is its own.
        self.in_scope = in_scope

    def shown(self) -> str:
        target = self.name or f"{self.directory}/{{{{{self.path}}}}}"
        return f"<!-- include:{target} -->"


def text_to_html(text: str) -> str:
    """Escape a text value and turn line breaks into paragraphs / `<br>`.

    Escaping happens first, so nothing from the data can produce markup.
    Curly braces are escaped as well: a value may legitimately contain `{{`,
    while `{{` in the rendered page always means an unfilled placeholder.

    `\\r\\n` -> `\\n`; two or more line breaks -> `</p><p>`; a single line break
    -> `<br>`.  Leading and trailing blank lines are dropped.  A multi-line
    field is therefore expected to be the only content of a `<p>…</p>`.
    """
    escaped = html.escape(text, quote=True).replace("{", "&#123;").replace("}", "&#125;")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
    escaped = _LEADING_BLANK_RE.sub("", escaped)
    escaped = _TRAILING_BLANK_RE.sub("", escaped)
    escaped = _PARAGRAPH_BREAK_RE.sub("</p><p>", escaped)
    return escaped.replace("\n", "<br>")


def lookup(path: str, context: dict, item: Any = MISSING) -> Any:
    """Resolve a template path; returns MISSING when the field does not exist.

    `field` / `a.b.c` are resolved against the page context, `.field` against
    the current item (of `each` or `with`) and `.` is the item itself.
    """
    if path == ".":
        return item
    if path.startswith("."):
        current: Any = item
        parts = path[1:].split(".")
    else:
        current = context
        parts = path.split(".")
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return MISSING
    return current


def is_truthy(value: Any) -> bool:
    """`if:` truthiness: false for missing, null, false, "", [], {} and 0."""
    if value is MISSING or value is None:
        return False
    return bool(value)


def format_value(
    value: Any, path: str = "?", line: int | None = None, name: str = "template"
) -> str:
    """Render a single `{{path}}` value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return text_to_html(value)
    if isinstance(value, (bool, int, float)):
        return text_to_html(str(value))
    if isinstance(value, (list, tuple)):
        raise TemplateError(
            f"field '{path}' is an array and cannot be inserted with {{{{…}}}}; "
            f"use <!-- each:{path} --> instead",
            line,
            name,
        )
    if isinstance(value, dict):
        raise TemplateError(
            f"field '{path}' is an object and cannot be inserted with {{{{…}}}}; "
            "insert one of its fields instead",
            line,
            name,
        )
    raise TemplateError(
        f"field '{path}' has unsupported type {type(value).__name__}", line, name
    )


def _shorten(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _walk(nodes: Sequence[Any]) -> Iterable[Any]:
    """Every node, depth first, including the contents of blocks."""
    for node in nodes:
        yield node
        if isinstance(node, _Block):
            yield from _walk(node.children)


class _Fragment:
    """One parsed fragment file."""

    __slots__ = ("nodes", "shown", "needs_item")

    def __init__(self, nodes: list[Any], shown: str, needs_item: bool):
        self.nodes = nodes
        #: The file as messages name it: `fragments/widgets/text.html`.
        self.shown = shown
        #: Uses the item of the place it is included from: `.field` outside its
        #: own `each`/`with`, directly or through a fragment it includes.
        self.needs_item = needs_item


class Fragments:
    """The fragments of the template by name (`widgets/text`).

    Every fragment is parsed and checked once, before any page is rendered:
    a fixed include names an existing fragment, fixed includes never form a
    cycle, and a directory that the data chooses from is not empty.  The set
    is fixed from then on, so a value from the data can only pick one of
    these files and never becomes a path.
    """

    def __init__(self, sources: dict[str, str] | None = None):
        self._items: dict[str, _Fragment] = {}
        for name, source in sorted((sources or {}).items()):
            shown = f"{FRAGMENTS_DIRNAME}/{name}{FRAGMENT_SUFFIX}"
            if not _FRAGMENT_NAME_RE.match(name):
                raise TemplateError(
                    "a fragment name uses a-z, 0-9 and '-' and starts with a letter "
                    "(at most 40 characters), '/' separates directories",
                    None,
                    shown,
                )
            nodes, needs_item = _parse(source, shown, fragment=True)
            self._items[name] = _Fragment(nodes, shown, needs_item)
        for fragment in self._items.values():
            self._check_includes(fragment.nodes, fragment.shown)
        self._check_cycles()
        self._propagate_needs_item()

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    def get(self, name: str) -> _Fragment:
        return self._items[name]

    def names(self, directory: str) -> list[str]:
        """Names a value may choose in `directory` (its files, not subdirectories)."""
        prefix = directory + "/"
        return sorted(
            name[len(prefix) :]
            for name in self._items
            if name.startswith(prefix) and "/" not in name[len(prefix) :]
        )

    def check_page(self, nodes: Sequence[Any], name: str) -> None:
        """Check the includes of the page template (`name`) before rendering.

        On top of the checks every fragment passes, a fragment that uses the
        current item may only be included where there is one.
        """
        self._check_includes(nodes, name)
        for node in _walk(nodes):
            if (
                isinstance(node, _Include)
                and node.name
                and not node.in_scope
                and self._items[node.name].needs_item
            ):
                raise TemplateError(
                    f"{node.shown()}: the fragment uses the current item ('.'), "
                    "include it inside <!-- each:… --> or <!-- with:… -->",
                    node.line,
                    name,
                )

    def _check_includes(self, nodes: Sequence[Any], name: str) -> None:
        for node in _walk(nodes):
            if not isinstance(node, _Include):
                continue
            if node.name:
                if node.name not in self._items:
                    raise TemplateError(
                        f"{node.shown()}: no fragment "
                        f"{FRAGMENTS_DIRNAME}/{node.name}{FRAGMENT_SUFFIX}",
                        node.line,
                        name,
                    )
            elif not self.names(node.directory):
                raise TemplateError(
                    f"{node.shown()}: no fragments in "
                    f"{FRAGMENTS_DIRNAME}/{node.directory}/",
                    node.line,
                    name,
                )

    def _check_cycles(self) -> None:
        done: set[str] = set()
        stack: list[str] = []

        def visit(current: str) -> None:
            stack.append(current)
            fragment = self._items[current]
            for node in _walk(fragment.nodes):
                if not isinstance(node, _Include) or not node.name or node.name in done:
                    continue
                if node.name in stack:
                    cycle = stack[stack.index(node.name) :] + [node.name]
                    raise TemplateError(
                        f"{node.shown()}: fragments include each other in a cycle: "
                        + " -> ".join(cycle),
                        node.line,
                        fragment.shown,
                    )
                visit(node.name)
            stack.pop()
            done.add(current)

        for name in self._items:
            if name not in done:
                visit(name)

    def _propagate_needs_item(self) -> None:
        # a fragment that includes one needing the item outside its own
        # each/with passes its item on, so it needs one as well
        changed = True
        while changed:
            changed = False
            for fragment in self._items.values():
                if fragment.needs_item:
                    continue
                if any(
                    isinstance(node, _Include)
                    and node.name
                    and not node.in_scope
                    and self._items[node.name].needs_item
                    for node in _walk(fragment.nodes)
                ):
                    fragment.needs_item = True
                    changed = True


class Template:
    """A parsed template; parse once, render for every page."""

    def __init__(
        self, source: str, name: str = "template", fragments: Fragments | None = None
    ):
        self.name = name
        self.fragments = fragments if fragments is not None else Fragments()
        self.nodes, _needs_item = _parse(source, name)
        self.fragments.check_page(self.nodes, name)

    def render(self, context: dict) -> str:
        out: list[str] = []
        _Renderer(context, self.fragments, out).nodes(self.nodes, MISSING, self.name, 0)
        result = "".join(out)
        check_rendered(result, self.name)
        return result


def parse_template(
    source: str, name: str = "template", fragments: Fragments | None = None
) -> Template:
    """Parse a template, raising TemplateError with a line number on failure."""
    return Template(source, name, fragments)


def check_rendered(output: str, name: str = "template") -> None:
    """Fail if the rendered page still contains template syntax."""
    problems: list[str] = []
    newlines = [m.start() for m in re.finditer("\n", output)]
    for match in _LEFTOVER_RE.finditer(output):
        line = bisect.bisect_left(newlines, match.start()) + 1
        problems.append(f"line {line}: '{_shorten(match.group(0), 20)}'")
        if len(problems) == 5:
            break
    if problems:
        raise TemplateError(
            "rendered output still contains template syntax: " + "; ".join(problems), None, name
        )


def _parse(source: str, name: str, fragment: bool = False) -> tuple[list[Any], bool]:
    """Parse a template or a fragment into (nodes, needs_item).

    In the page template `.field` is only allowed inside `each`/`with`.  A
    fragment may use it anywhere: outside its own `each`/`with` it means the
    item of the place the fragment is included from, and `needs_item` says so.
    """
    newlines = [m.start() for m in re.finditer("\n", source)]

    def line_at(pos: int) -> int:
        return bisect.bisect_left(newlines, pos) + 1

    root: list[Any] = []
    stack: list[_Block] = []
    needs_item = False

    def children() -> list[Any]:
        return stack[-1].children if stack else root

    def in_scope() -> bool:
        return any(block.kind in ("each", "with") for block in stack)

    def check_syntax(path: str, line: int, shown: str) -> None:
        if not path:
            raise TemplateError(f"{shown} has no field path", line, name)
        if not _PATH_RE.match(path):
            raise TemplateError(f"{shown} has an invalid field path", line, name)

    def check_path(path: str, line: int, shown: str) -> None:
        nonlocal needs_item
        check_syntax(path, line, shown)
        if path.startswith(".") and not in_scope():
            if not fragment:
                raise TemplateError(
                    f"{shown} refers to the current item but is not inside "
                    "<!-- each:… --> or <!-- with:… -->",
                    line,
                    name,
                )
            needs_item = True

    def add_include(match: re.Match, line: int, shown: str) -> None:
        fixed, directory, path = match.groups()
        if fixed:
            children().append(_Include(fixed, "", "", line, in_scope()))
            return
        check_syntax(path, line, shown)
        if not path.startswith(".") or path == ".":
            raise TemplateError(
                f"{shown}: a fragment is chosen by a field of the current item, "
                "write {{.field}}",
                line,
                name,
            )
        if not in_scope():
            # the item changes before every choice, so a fragment can never
            # choose itself again by the item it was chosen for
            raise TemplateError(
                f"{shown} must be inside <!-- each:… --> or <!-- with:… -->", line, name
            )
        children().append(_Include("", directory.rstrip("/"), path, line, True))

    def add_literal(literal: str, offset: int) -> None:
        if not literal:
            return
        stray = _BRACES_RE.search(literal)
        if stray:
            raise TemplateError(
                f"unmatched '{stray.group(0)}'", line_at(offset + stray.start()), name
            )
        children().append(literal)

    def add_text(start: int, end: int) -> None:
        text = source[start:end]
        pos = 0
        for match in _PLACEHOLDER_RE.finditer(text):
            add_literal(text[pos : match.start()], start + pos)
            line = line_at(start + match.start())
            path = match.group(1).strip()
            shown = "{{" + _shorten(match.group(1), 40) + "}}"
            check_path(path, line, shown)
            children().append(_Var(path, line))
            pos = match.end()
        add_literal(text[pos:], start + pos)

    pos = 0
    for match in _COMMENT_RE.finditer(source):
        inner = match.group(1).strip()
        if not _DIRECTIVE_LIKE_RE.match(inner):
            continue  # an ordinary HTML comment: keep it as text
        add_text(pos, match.start())
        pos = match.end()
        line = line_at(match.start())
        shown = _shorten(match.group(0))

        if inner in ("endif", "endeach", "endwith"):
            kind = inner[len("end") :]
            if not stack:
                raise TemplateError(
                    f"{shown} without a matching <!-- {kind}:… -->", line, name
                )
            open_block = stack[-1]
            if open_block.kind != kind:
                raise TemplateError(
                    f"{shown} does not match <!-- {open_block.kind}:{open_block.path} -->"
                    f" opened at line {open_block.line}",
                    line,
                    name,
                )
            stack.pop()
            continue

        include_match = _INCLUDE_RE.match(inner)
        if include_match:
            add_include(include_match, line, shown)
            continue
        if inner[: len("include")].lower() == "include":
            raise TemplateError(
                f"malformed directive {shown} (expected <!-- include:dir/name --> or "
                "<!-- include:dir/{{.field}} -->, all lowercase; a name uses a-z, "
                "0-9 and '-' and starts with a letter)",
                line,
                name,
            )

        if_match = _IF_RE.match(inner)
        each_match = _EACH_RE.match(inner)
        with_match = _WITH_RE.match(inner)
        if if_match:
            kind, negate, path = "if", bool(if_match.group(1)), if_match.group(2)
        elif each_match:
            kind, negate, path = "each", False, each_match.group(1)
        elif with_match:
            kind, negate, path = "with", False, with_match.group(1)
            if path == ".":
                raise TemplateError(f"{shown}: '.' is the current item already", line, name)
        else:
            raise TemplateError(
                f"malformed directive {shown} (expected <!-- if:path -->, "
                "<!-- if:!path -->, <!-- endif -->, <!-- each:path -->, "
                "<!-- endeach -->, <!-- with:path -->, <!-- endwith --> or "
                "<!-- include:dir/name -->, all lowercase)",
                line,
                name,
            )
        check_path(path, line, shown)
        block = _Block(kind, path, negate, line)
        children().append(block)
        stack.append(block)

    add_text(pos, len(source))

    if stack:
        open_block = stack[-1]
        raise TemplateError(
            f"<!-- {open_block.kind}:{open_block.path} --> is not closed "
            f"(missing <!-- end{open_block.kind} -->)",
            open_block.line,
            name,
        )
    return root, needs_item


class _Renderer:
    """Renders parsed nodes of the template and its fragments into `out`."""

    __slots__ = ("context", "fragments", "out")

    def __init__(self, context: dict, fragments: Fragments, out: list[str]):
        self.context = context
        self.fragments = fragments
        self.out = out

    def nodes(self, nodes: Sequence[Any], item: Any, name: str, depth: int) -> None:
        """Render `nodes` of the file `name`; `depth` counts nested fragments."""
        context, out = self.context, self.out
        for node in nodes:
            if isinstance(node, str):
                out.append(node)
            elif isinstance(node, _Var):
                value = lookup(node.path, context, item)
                if value is MISSING:
                    raise TemplateError(f"field '{node.path}' not found", node.line, name)
                out.append(format_value(value, node.path, node.line, name))
            elif isinstance(node, _Include):
                self.include(node, item, name, depth)
            elif node.kind == "if":
                if is_truthy(lookup(node.path, context, item)) is not node.negate:
                    self.nodes(node.children, item, name, depth)
            elif node.kind == "with":
                value = lookup(node.path, context, item)
                if value is MISSING:
                    raise TemplateError(
                        f"<!-- with:{node.path} -->: field '{node.path}' not found",
                        node.line,
                        name,
                    )
                if value is None or value is False:
                    continue
                if not isinstance(value, dict):
                    raise TemplateError(
                        f"<!-- with:{node.path} -->: field '{node.path}' is "
                        f"{json_type(value)}, expected an object",
                        node.line,
                        name,
                    )
                if value:
                    self.nodes(node.children, value, name, depth)
            else:  # each
                sequence = lookup(node.path, context, item)
                if sequence is MISSING:
                    raise TemplateError(
                        f"<!-- each:{node.path} -->: field '{node.path}' not found",
                        node.line,
                        name,
                    )
                if sequence is None:
                    continue
                if not isinstance(sequence, (list, tuple)):
                    raise TemplateError(
                        f"<!-- each:{node.path} -->: field '{node.path}' is "
                        f"{json_type(sequence)}, expected an array",
                        node.line,
                        name,
                    )
                for element in sequence:
                    self.nodes(node.children, element, name, depth)

    def include(self, node: _Include, item: Any, name: str, depth: int) -> None:
        target = node.name or self.choose(node, item, name)
        if depth >= MAX_INCLUDE_DEPTH:
            raise TemplateError(
                f"{node.shown()}: fragments are nested deeper than "
                f"{MAX_INCLUDE_DEPTH} levels",
                node.line,
                name,
            )
        fragment = self.fragments.get(target)
        try:
            self.nodes(fragment.nodes, item, fragment.shown, depth + 1)
        except TemplateError as exc:
            raise exc.via(name, node.line) from None

    def choose(self, node: _Include, item: Any, name: str) -> str:
        """The fragment named by the value of `node.path`.

        The value comes from the data: it is only compared with the names of
        the loaded files (one part, no '/') and never quoted in a message.
        """
        value = lookup(node.path, self.context, item)
        if value is MISSING:
            raise TemplateError(
                f"{node.shown()}: field '{node.path}' not found", node.line, name
            )
        if not isinstance(value, str) or not _SEGMENT_RE.match(value):
            raise TemplateError(
                f"{node.shown()}: the value of '{node.path}' is not a fragment name",
                node.line,
                name,
            )
        target = f"{node.directory}/{value}"
        if target not in self.fragments:
            raise TemplateError(
                f"{node.shown()}: no fragment in {FRAGMENTS_DIRNAME}/{node.directory}/ "
                f"for the value of '{node.path}' "
                f"(known: {', '.join(self.fragments.names(node.directory))})",
                node.line,
                name,
            )
        return target


# --------------------------------------------------------------------------
# Data loading and validation
# --------------------------------------------------------------------------


def check_base_path(value: Any) -> str:
    """`build --base-path`: `/` or `/seg[/seg…]`, segments of A-Z, a-z, 0-9,
    `_` and `-`; a trailing `/` is dropped.  `ValueError` names the problem,
    never the value."""
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or _BASE_PATH_RE.fullmatch(value) is None
    ):
        raise ValueError(
            "must be a path from the root of the site: '/' or segments of A-Z, a-z, "
            "0-9, '_' and '-', each after a single '/', e.g. /menu (no '.' or '..', "
            "'%', '?', '#', scheme, host or spaces)"
        )
    normalized = value.rstrip("/") or "/"
    if len(normalized) > MAX_BASE_PATH_LENGTH:
        raise ValueError(f"must be at most {MAX_BASE_PATH_LENGTH} characters long")
    return normalized


def assets_url_path(base_path: str = DEFAULT_BASE_PATH) -> str:
    """`<base path>/assets`: the URL path of the files the pages share."""
    return f"{base_path.rstrip('/')}/{ASSETS_DIRNAME}"


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not allowed in JSON data")


def read_json(path: Path, report: Report, known: Collection[str] | None = None) -> Any:
    """Read a JSON document, reporting I/O and syntax problems (never values).

    A key repeated within one object is an error as well: the standard parser
    would silently keep the last value only.  With `known` the message shows
    a repeated key only when it is one of these names (the keys of the guest
    records may be somebody's name).
    """
    shown = display_path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        report.error(f"{shown}: file not found")
        return MISSING
    except IsADirectoryError:
        report.error(f"{shown}: expected a file, found a directory")
        return MISSING
    except UnicodeDecodeError as exc:
        report.error(f"{shown}: not valid UTF-8 (at byte {exc.start})")
        return MISSING
    except OSError as exc:
        report.error(f"{shown}: cannot read the file ({exc.strerror})")
        return MISSING
    try:
        value, duplicates = data_tools.parse_json(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        report.error(
            f"{shown}: invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        )
        return MISSING
    except ValueError as exc:
        report.error(f"{shown}: invalid JSON: {exc}")
        return MISSING
    for duplicate in duplicates:
        report.error(f"{shown}: {duplicate.describe(known)}")
    return MISSING if duplicates else value


# --------------------------------------------------------------------------
# HTML comments
# --------------------------------------------------------------------------

#: What may follow the text of a comment: `-->`, `--!>`, or the `>` / `->` of an
#: abruptly closed `<!-->` / `<!--->`.
_COMMENT_END_RE = re.compile(r"-{0,2}!?\s*>")


class _CommentLocator(HTMLParser):
    """Finds the HTML comments of a document (never the `<!--` inside scripts,
    styles or attribute values, which is why this is not a regular expression).
    """

    def __init__(self, document: str):
        super().__init__(convert_charrefs=False)
        self.document = document
        self.spans: list[tuple[int, int]] = []
        self._line_starts = [0] + [m.end() for m in re.finditer("\n", document)]

    def handle_comment(self, data: str) -> None:
        line, column = self.getpos()
        start = self._line_starts[line - 1] + column
        document = self.document
        if document.startswith("<!--", start):
            end = start + 4 + len(data)
            closing = _COMMENT_END_RE.match(document, end)
            end = closing.end() if closing else len(document)
        else:  # a "bogus comment" such as <!x> or </ x>: it ends at the next '>'
            closing_at = document.find(">", start)
            end = closing_at + 1 if closing_at >= 0 else len(document)
        self.spans.append((start, end))


#: Markup that `html.parser` and browsers read differently (a browser ends
#: `<![CDATA[ … ]]>` and `<? … ?>` at the first `>`, the parser may not).
_UNSAFE_MARKUP_RE = re.compile(r"<!\[|<\?")


def find_unsafe_markup(document: str) -> tuple[int, str] | None:
    """(line, message) for the first `<![…` or `<?…`, which are not allowed."""
    match = _UNSAFE_MARKUP_RE.search(document)
    if match is None:
        return None
    line = document.count("\n", 0, match.start()) + 1
    return line, f"'{match.group(0)}…' (CDATA sections, processing instructions) is not allowed"


def strip_html_comments(document: str, name: str = "template") -> str:
    """Remove every HTML comment, so that template notes are never published."""
    unsafe = find_unsafe_markup(document)
    if unsafe:
        raise TemplateError(unsafe[1], unsafe[0], name)
    if "<!" not in document and "</" not in document:
        return document
    locator = _CommentLocator(document)
    locator.feed(document)
    locator.close()
    if not locator.spans:
        return document
    parts: list[str] = []
    position = 0
    for start, end in locator.spans:
        if start < position:  # pragma: no cover - spans never overlap
            continue
        parts.append(document[position:start])
        position = end
    parts.append(document[position:])
    return "".join(parts)


# --------------------------------------------------------------------------
# Checks on the finished output
# --------------------------------------------------------------------------


class OutputError(ValidationError):
    """The finished output failed one or more checks (all of them are listed)."""


class OutputStats(NamedTuple):
    """What `check_output` counted."""

    files: int
    size: int


#: Attributes whose value is a URL that the browser fetches (or submits to).
_URL_ATTRIBUTES = frozenset(
    {
        "src",
        "poster",
        "href",
        "xlink:href",
        "action",
        "formaction",
        "background",
        "manifest",
        "ping",
    }
)
_SRCSET_ATTRIBUTES = frozenset({"srcset", "imagesrcset"})
#: Elements that embed foreign documents (or redirect every URL of the page).
_FORBIDDEN_ELEMENTS = frozenset(
    {"iframe", "frame", "frameset", "object", "embed", "applet", "base"}
)
_LINK_ELEMENTS = frozenset({"a", "area"})
_SVG_ANIMATION_ELEMENTS = frozenset(
    {"set", "animate", "animatemotion", "animatetransform", "animatecolor"}
)
#: `<meta>` entries whose `content` is a URL.
_META_URL_KEYS = frozenset(
    {
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "og:url",
        "og:video",
        "og:video:url",
        "og:audio",
        "twitter:image",
        "twitter:image:src",
        "twitter:player",
        "msapplication-tileimage",
    }
)
_SCHEME_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
#: Schemes that are named in messages; anything else before a ':' may be text.
_KNOWN_SCHEMES = frozenset(
    {"http", "https", "mailto", "tel", "sms", "ftp", "blob", "file", "javascript",
     "vbscript", "data", "about", "ws", "wss"}
)
#: Text that a browser may read as markup where the parser sees plain text
#: (`<svg><title><img …>`): a '<' followed by a letter, '/', '!' or '?'.
_MARKUP_LIKE_RE = re.compile(r"<[A-Za-z/!?]")
_EXTERNAL_TEXT_RE = re.compile(r"(?:https?:)?//[A-Za-z0-9\[]", re.IGNORECASE)
_URL_WHITESPACE_RE = re.compile(r"[\t\n\r]")
_URL_TRIM = "".join(map(chr, range(33)))  # C0 control characters and space
#: URLs made of these characters only are quoted in messages; anything else may
#: be text that a template put into a URL by mistake, and is not echoed.
_PLAIN_URL_RE = re.compile(r"[A-Za-z0-9/._~%?=&#+,:;@-]*\Z")
_HTML_SPACE = " \t\n\f\r"


def _clean_url(value: str) -> str:
    """The URL as a browser reads it: trimmed, without tabs and line breaks."""
    return _URL_WHITESPACE_RE.sub("", value.strip(_URL_TRIM))


def _show_url(url: str) -> str:
    """A URL for an error message: external URLs are cut down to the host (the
    rest may carry data), everything else is shortened."""
    url = _clean_url(url)
    if url.lower().startswith("data:"):
        return _shorten(re.split(r"[;,]", url, maxsplit=1)[0], 40) + ",…"
    scheme = _SCHEME_RE.match(url)
    if scheme and scheme.group(1).lower() not in ("http", "https"):
        # e.g. mailto: - the rest is data, and so is an unknown "scheme"
        name = scheme.group(1).lower()
        return f"{name}:…" if name in _KNOWN_SCHEMES else "…:"
    if scheme or url.replace("\\", "/").startswith("//"):
        head = re.match(r"[^/\\?#]*[/\\]{0,2}[^/\\?#]*", url)
        shown = head.group(0) if head else url
        if not _PLAIN_URL_RE.match(shown):
            return f"{scheme.group(0) if scheme else ''}//…"
        return _shorten(shown, 60) + ("/…" if len(shown) < len(url) else "")
    return _shorten(url, 80) if _PLAIN_URL_RE.match(url) else "…"


def _classify_url(value: str) -> tuple[str, str]:
    """(kind, cleaned URL); kind is one of `empty`, `fragment`, `local`,
    `relative`, `external`, `data`, `script`, `scheme` or `malformed`."""
    url = _clean_url(value)
    if not url:
        return "empty", url
    if url.startswith("#"):
        return "fragment", url
    scheme = _SCHEME_RE.match(url)
    if scheme:
        name = scheme.group(1).lower()
        if name in ("http", "https"):
            return "external", url
        if name == "data":
            return "data", url
        if name in ("javascript", "vbscript"):
            return "script", url
        return "scheme", url
    if "\\" in url:
        return "malformed", url  # browsers read '\' as '/': "/\host" is external
    if url.startswith("//"):
        return "external", url
    if url.startswith("/"):
        return "local", url
    return "relative", url


def _url_path(url: str) -> str:
    """The decoded path of a URL, without its query and fragment."""
    return unquote(url.split("#", 1)[0].split("?", 1)[0])


def _within_base(url: str, base_path: str = DEFAULT_BASE_PATH) -> bool:
    """True when a root-absolute URL lies under `base_path` (always for `/`)."""
    prefix = base_path.rstrip("/")
    path = _url_path(url)
    return not prefix or path == prefix or path.startswith(f"{prefix}/")


def _is_plain_path(path: str) -> bool:
    """True when a decoded path from the root has no empty, `.` or `..`
    segment and no `\\`; a trailing `/` stands for the index page of a
    directory."""
    segments = path.split("/")[1:]
    if path.endswith("/"):
        segments = segments[:-1]
    return "\\" not in path and not any(segment in ("", ".", "..") for segment in segments)


def _local_file(url: str, base_path: str = DEFAULT_BASE_PATH) -> str | None:
    """Output file that a root-absolute URL points at; None if it is not plain
    or lies outside `base_path` (the output is published under it)."""
    if not _within_base(url, base_path):
        return None
    path = _url_path(url)[len(base_path.rstrip("/")) :] or "/"
    if not _is_plain_path(path):
        return None
    return (path + PAGE_FILE if path.endswith("/") else path)[1:]


def _data_url_type(url: str) -> str:
    return re.split(r"[;,]", url[5:], maxsplit=1)[0].strip().lower()


def _srcset_urls(value: str) -> list[str]:
    """The URLs of a `srcset` (a URL may contain commas, e.g. `data:` URLs)."""
    urls: list[str] = []
    position, length = 0, len(value)
    while position < length:
        while position < length and (
            value[position] in _HTML_SPACE or value[position] == ","
        ):
            position += 1
        start = position
        while position < length and value[position] not in _HTML_SPACE:
            position += 1
        url = value[start:position]
        if url.endswith(","):
            url = url.rstrip(",")
        else:  # skip the descriptors up to the next candidate
            depth = 0
            while position < length:
                char = value[position]
                position += 1
                if char == "(":
                    depth += 1
                elif char == ")" and depth:
                    depth -= 1
                elif char == "," and not depth:
                    break
        if url:
            urls.append(url)
    return urls


class _UrlPolicy:
    """Shared URL rules of the HTML and CSS checks; collects (line, problem)."""

    def __init__(
        self,
        exists: Callable[[str], bool],
        is_dir: Callable[[str], bool] | None = None,
        base: str | None = None,
        base_path: str = DEFAULT_BASE_PATH,
    ):
        self.exists = exists
        self.is_dir = is_dir if is_dir is not None else (lambda _path: False)
        #: Directory of the style sheet being checked ("" is the root); None
        #: for HTML, where relative URLs are not allowed at all.
        self.base = base
        #: The path the output is published under (`build --base-path`): a
        #: local URL must lie under it.
        self.base_path = base_path
        self.problems: list[tuple[int, str]] = []

    def show_path(self, url: str) -> str:
        """A local or relative URL for a message.

        Only the base path, the directories that exist in the output and the
        extension of a type the build writes are shown: the rest may be text
        that a template put into a path by mistake.
        """
        path = _clean_url(url).split("#", 1)[0].split("?", 1)[0]
        absolute = path.startswith("/")
        segments = [segment for segment in path.split("/") if segment]
        kept: list[str] = []
        if absolute:
            base = [segment for segment in self.base_path.split("/") if segment]
            start = len(base) if segments[: len(base)] == base else 0
            kept = segments[:start]
            inside: list[str] = []
            for segment in segments[start:]:
                candidate = "/".join([*inside, unquote(segment)])
                if not _PLAIN_URL_RE.match(segment) or not self.is_dir(candidate):
                    break
                inside.append(segment)
            kept += inside
        lead = "/" if absolute else ""
        if len(kept) == len(segments):
            return lead + "/".join(kept) + ("/" if kept else "")
        extension = os.path.splitext(segments[-1])[1].lower()
        if extension not in SHOWN_EXTENSIONS:
            extension = ""
        return lead + "/".join([*kept, "…"]) + extension

    def _relative_to_stylesheet(self, line: int, where: str, url: str) -> None:
        """A relative `url()` of a CSS file: resolved against the file itself."""
        path = unquote(url.split("#", 1)[0].split("?", 1)[0])
        target = posixpath.normpath(posixpath.join(self.base or "", path))
        if target == ".." or target.startswith(("../", "/")):
            self.problem(line, f"{where}: '{self.show_path(url)}' points outside the output")
        elif not self.exists(target):
            self.problem(
                line,
                f"{where}: '{self.show_path(url)}' (relative to the style sheet) "
                "does not exist in the output",
            )

    def problem(self, line: int, message: str) -> None:
        self.problems.append((line, message))

    def _common(self, line: int, where: str, kind: str, url: str, what: str) -> bool:
        """Rules shared by resources and links; True when the URL is settled."""
        if kind == "fragment":
            return True
        if kind == "local":
            target = _local_file(url, self.base_path)
            if not _within_base(url, self.base_path):
                self.problem(line, f"{where}: '{self.show_path(url)}' points outside the output")
            elif target is None:
                self.problem(
                    line, f"{where}: '{self.show_path(url)}' is not a plain absolute path"
                )
            elif not self.exists(target):
                self.problem(
                    line, f"{where}: '{self.show_path(url)}' does not exist in the output"
                )
        elif kind == "empty":
            self.problem(line, f"{where}: the URL is empty")
        elif kind == "relative" and self.base is not None:
            self._relative_to_stylesheet(line, where, url)
        elif kind == "relative":
            self.problem(
                line,
                f"{where}: relative path '{self.show_path(url)}'; {what} must be "
                f"absolute from the site root (start with '{self.base_path.rstrip('/')}/')",
            )
        elif kind == "script":
            self.problem(line, f"{where}: script URL '{_show_url(url)}' is not allowed")
        else:
            return False
        return True

    def check_resource(
        self,
        line: int,
        where: str,
        value: str,
        *,
        data_images: bool = True,
        empty_data: bool = False,
    ) -> None:
        """A URL that is fetched when the page loads: local files only."""
        kind, url = _classify_url(value)
        if self._common(line, where, kind, url, "resource paths"):
            return
        if kind == "external":
            self.problem(
                line,
                f"{where}: external URL '{_show_url(url)}'; every resource must be "
                "a local file",
            )
        elif kind == "data":
            allowed = data_images and _data_url_type(url).startswith("image/")
            if empty_data and url.lower() == "data:,":
                allowed = True
            if not allowed:
                self.problem(
                    line,
                    f"{where}: '{_show_url(url)}' - data: URLs are only allowed "
                    "for images and icons",
                )
        else:
            shown = _show_url(url) if kind == "scheme" else self.show_path(url)
            self.problem(line, f"{where}: URL '{shown}' is not allowed")

    def check_link(self, line: int, where: str, value: str) -> None:
        """`<a href>`: a file of the output or a fragment."""
        kind, url = _classify_url(value)
        if self._common(line, where, kind, url, "links"):
            return
        if kind == "external":
            self.problem(line, f"{where}: external link '{_show_url(url)}' is not allowed")
        else:  # mailto:, tel:, data: and other schemes
            shown = _show_url(url) if kind in ("scheme", "data") else self.show_path(url)
            self.problem(line, f"{where}: link '{shown}' is not allowed")


_CSS_STRING = r'"(?:[^"\\\n]|\\.)*"' + "|" + r"'(?:[^'\\\n]|\\.)*'"
_CSS_COMMENT_OR_STRING_RE = re.compile(rf"/\*.*?(?:\*/|\Z)|{_CSS_STRING}", re.DOTALL)
_CSS_NAMESPACE_RE = re.compile(r"@namespace\b[^;{}]*;?", re.IGNORECASE)
_CSS_URL_RE = re.compile(
    rf"(?<![\w-])url\(\s*({_CSS_STRING}|[^)]*?)\s*(?:\)|\Z)", re.IGNORECASE
)
_CSS_IMPORT_RE = re.compile(rf"@import\s*({_CSS_STRING})", re.IGNORECASE)
_CSS_IMPORT_BEFORE_RE = re.compile(r"@import\s*\Z", re.IGNORECASE)
_CSS_STRING_RE = re.compile(_CSS_STRING)


def _blank(match: re.Match) -> str:
    """Replacement that keeps the line numbers of the rest of the text."""
    return "\n" * match.group(0).count("\n") or " "


def strip_css_comments(text: str) -> str:
    """CSS without comments (strings are left alone, line numbers are kept)."""
    return _CSS_COMMENT_OR_STRING_RE.sub(
        lambda match: _blank(match) if match.group(0).startswith("/*") else match.group(0),
        text,
    )


def _css_string_value(token: str) -> str:
    return token[1:-1] if len(token) >= 2 and token[0] in "\"'" else token


_CSS_CONTINUATION_RE = re.compile(r"\\[\n\r\f]")
#: A string that starts with a URL scheme (`image-set('http:host/x')`); "12:30"
#: and "Note: text" are not URLs, `data:` is judged where it is used.
_CSS_SCHEME_STRING_RE = re.compile(r"(?!data:)[a-z][a-z0-9+.-]*:(?=\S)", re.IGNORECASE)
_CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\([^\n])")
_CSS_NAME = r"(?:[\w-]|\\[0-9a-fA-F]{1,6}\s?|\\[^\n0-9a-fA-F])+"
_CSS_FUNCTION_RE = re.compile(rf"({_CSS_NAME})\(")
_CSS_AT_RULE_RE = re.compile(rf"@({_CSS_NAME})")
_CSS_PLAIN_NAME_RE = re.compile(r"[\w-]+\Z")


def _css_unescape(text: str) -> str:
    def decode(match: re.Match) -> str:
        if match.group(1):
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF else "\ufffd"
        return match.group(2)

    return _CSS_ESCAPE_RE.sub(decode, text)


def check_css(
    text: str, policy: _UrlPolicy, where: str = "CSS", first_line: int = 1
) -> None:
    """`url()`, `@import` and URL-like strings of a style sheet (or of a
    `style` attribute) must point at local files.

    A browser decodes CSS escapes (`u\\72l(…)` is `url(…)`), so escapes are
    refused wherever they could hide a URL: in function and at-rule names and
    inside `url()` / `@import`; other strings are checked decoded as well.
    """
    # first of all: a backslash before a line break continues a string, which
    # would split a URL across lines and hide it from everything below
    continuation = _CSS_CONTINUATION_RE.search(text)
    if continuation:
        policy.problem(
            first_line + text.count("\n", 0, continuation.start()),
            f"{where}: a backslash before a line break is not allowed in CSS",
        )
        return
    text = _CSS_NAMESPACE_RE.sub(_blank, strip_css_comments(text))

    def line_at(offset: int) -> int:
        return first_line + text.count("\n", 0, offset)

    def check_url(offset: int, what: str, value: str, images: bool) -> None:
        if "\\" in value and not _clean_url(value).lower().startswith("data:"):
            policy.problem(
                line_at(offset), f"{where} {what}: CSS escapes are not allowed in URLs"
            )
        else:
            policy.check_resource(line_at(offset), f"{where} {what}", value, data_images=images)

    without_strings = _CSS_STRING_RE.sub(lambda match: " " * len(match.group(0)), text)
    for match in _CSS_AT_RULE_RE.finditer(without_strings):
        if "\\" in match.group(1):
            policy.problem(
                line_at(match.start()), f"{where}: CSS escapes are not allowed in at-rule names"
            )
    for match in _CSS_FUNCTION_RE.finditer(without_strings):
        name = match.group(1)
        if "\\" in name and _CSS_PLAIN_NAME_RE.match(_css_unescape(name)):
            policy.problem(
                line_at(match.start()),
                f"{where}: CSS escapes are not allowed in function names",
            )

    covered: list[tuple[int, int]] = []
    for match in _CSS_IMPORT_RE.finditer(text):
        covered.append(match.span())
        check_url(match.start(), "@import", _css_string_value(match.group(1)), False)
    for match in _CSS_URL_RE.finditer(text):
        covered.append(match.span())
        before = text[max(0, match.start() - 40) : match.start()]
        is_import = _CSS_IMPORT_BEFORE_RE.search(before) is not None
        check_url(
            match.start(),
            "@import" if is_import else "url()",
            _css_string_value(match.group(1)),
            not is_import,
        )
    for match in _CSS_STRING_RE.finditer(text):
        if any(start <= match.start() < end for start, end in covered):
            continue
        value = _css_string_value(match.group(0))
        if any(
            _EXTERNAL_TEXT_RE.match(candidate.strip())
            or _CSS_SCHEME_STRING_RE.match(candidate.strip())
            for candidate in (value, _css_unescape(value))
        ):
            policy.problem(
                line_at(match.start()),
                f"{where}: external URL '{_show_url(_css_unescape(value))}' in a string; "
                "every resource must be a local file",
            )


class _HtmlChecker(HTMLParser):
    """Walks one HTML document and applies the URL and script rules."""

    def __init__(self, policy: _UrlPolicy):
        # text is reported as written: an escaped "&lt;!--" in a guest's note
        # is text, not the start of a comment (attribute values are decoded)
        super().__init__(convert_charrefs=False)
        self.policy = policy
        self._in_script = False

    @property
    def line(self) -> int:
        return self.getpos()[0]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        policy, line = self.policy, self.line
        values: dict[str, str] = {}
        for name, value in attrs:  # a repeated attribute: the first one wins
            values.setdefault(name, value or "")
        if tag in _FORBIDDEN_ELEMENTS:
            policy.problem(line, f"<{tag}> is not allowed")
            return
        if tag == "style":
            # also closes a gap: inside <svg> a browser parses the content of
            # <style> as markup, while the parser takes it for text
            policy.problem(
                line, "<style> elements are not allowed; styles must be files in assets/"
            )
        if tag == "script":
            self._in_script = bool(values.get("src", "").strip())
            if not self._in_script:
                policy.problem(
                    line, "inline <script> is not allowed; scripts must be files in assets/"
                )
            if "href" in values or "xlink:href" in values:
                policy.problem(line, "<script href> (an SVG script) is not allowed")
        if tag in _SVG_ANIMATION_ELEMENTS and values.get(
            "attributename", ""
        ).strip().lower() in ("href", "xlink:href"):
            policy.problem(line, f"<{tag}>: animating 'href' is not allowed")

        for name, value in values.items():
            where = f"<{tag} {name}>"
            if name.startswith("on") and len(name) > 2:
                policy.problem(line, f"{where}: inline event handlers are not allowed")
            elif name in _SRCSET_ATTRIBUTES:
                urls = _srcset_urls(value)
                if not urls:
                    policy.problem(line, f"{where}: the URL is empty")
                for url in urls:
                    policy.check_resource(line, where, url)
            elif name in _URL_ATTRIBUTES:
                if tag in _LINK_ELEMENTS and name == "href":
                    policy.check_link(line, where, value)
                else:
                    rel = values.get("rel", "").lower().split()
                    is_icon = tag == "link" and "icon" in rel
                    policy.check_resource(
                        line,
                        where,
                        value,
                        data_images=is_icon or tag not in ("script", "a", "area", "link"),
                        empty_data=is_icon,
                    )
            elif name == "style":
                check_css(value, policy, f"<{tag} style>", line)

        if tag == "meta":
            self._check_meta(values, line)

    def _check_meta(self, values: dict, line: int) -> None:
        content = values.get("content", "")
        key = (values.get("property") or values.get("name") or "").strip().lower()
        if values.get("http-equiv", "").strip().lower() == "refresh":
            self.policy.problem(line, '<meta http-equiv="refresh"> is not allowed')
            return
        if key in _META_URL_KEYS:
            # a path from the site root, a file of the output: the build never
            # knows the address of the site, an absolute URL is an error
            self.policy.check_resource(line, f"<meta {key}>", content)
            return
        external = _EXTERNAL_TEXT_RE.search(content)
        if external:
            shown = _show_url(content[external.start() :].split()[0])
            self.policy.problem(
                line, f"<meta content>: external URL '{shown}' is not allowed"
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            # a browser may read this as markup (inside <svg>), the parser does not
            if data.strip():
                self.policy.problem(self.line, "<script src> must be empty")
        elif _MARKUP_LIKE_RE.search(data):
            # Escaped text ("&lt;img") never gets here as '<'.  A literal '<'
            # in text means that the parser took something for text - the
            # content of <title>/<textarea> inside <svg>, an unterminated
            # comment - which a browser may read as elements.
            self.policy.problem(
                self.line, "markup-like text is not allowed (write '<' as '&lt;')"
            )

    def handle_decl(self, decl: str) -> None:
        if not decl.strip().lower().startswith("doctype"):
            self.policy.problem(self.line, "'<!…>' declarations are not allowed")

    def handle_comment(self, data: str) -> None:
        self.policy.problem(self.line, "HTML comment left in the output")


def check_html(
    document: str,
    exists: Callable[[str], bool],
    is_dir: Callable[[str], bool] | None = None,
    base_path: str = DEFAULT_BASE_PATH,
) -> list[tuple[int, str]]:
    """Problems of one HTML document as (line, message) pairs.

    `exists` tells whether a file (relative path with '/') is in the output,
    `is_dir` does the same for directories (only used to word the messages).
    The output is published under `base_path`: a local URL outside it points
    outside the output, one inside it is looked up without the base path.
    Whatever the parser may read differently from a browser is an error;
    so is any absolute URL, `<meta>` links (`og:image`) included.
    """
    policy = _UrlPolicy(exists, is_dir, base_path=base_path)
    leftover = _LEFTOVER_RE.search(document)
    if leftover:
        policy.problem(
            document.count("\n", 0, leftover.start()) + 1,
            f"template syntax left in the output: '{_shorten(leftover.group(0), 20)}'",
        )
    unsafe = find_unsafe_markup(document)
    if unsafe:
        policy.problem(*unsafe)
    checker = _HtmlChecker(policy)
    checker.feed(document)
    checker.close()
    return policy.problems


def check_stylesheet(
    text: str,
    exists: Callable[[str], bool],
    is_dir: Callable[[str], bool] | None = None,
    base: str = "",
    base_path: str = DEFAULT_BASE_PATH,
) -> list[tuple[int, str]]:
    """Problems of one CSS file as (line, message) pairs.

    `base` is the directory of the file inside the output: relative `url()`s
    are resolved against it and must stay inside the output; root-absolute
    ones must lie under `base_path` (see `check_html`).
    """
    policy = _UrlPolicy(exists, is_dir, base, base_path)
    check_css(text, policy)
    return policy.problems


#: Markup of an SVG file that pulls in other documents or defines entities
#: (an entity can hide anything from the checks below).
_SVG_UNSAFE_MARKUP = (
    (re.compile(r"<!ENTITY", re.IGNORECASE), "'<!ENTITY' declarations are not allowed"),
    (re.compile(r"<\?xml-stylesheet", re.IGNORECASE), "'<?xml-stylesheet' is not allowed"),
)
_SVG_URL_ATTRIBUTES = frozenset({"href", "xlink:href", "src"})
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
_XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
#: Prefixes that mean SVG itself even when the file declares nothing.
_SVG_OWN_PREFIXES = frozenset({"svg", "xlink"})
#: Prefixes that spell HTML by habit; the namespace they are bound to decides,
#: these are only what an undeclared prefix is read as.
_SVG_HTML_PREFIXES = frozenset({"xhtml", "html"})
#: Attributes that a browser acts on but the URL rules here cannot follow:
#: a list of candidate URLs, and a different base for every relative one.
_SVG_REFUSED_ATTRIBUTES = frozenset({*_SRCSET_ATTRIBUTES, "xml:base"})


def _local_name(tag: str) -> str:
    """`svg:script` -> `script`: a namespace prefix does not change the element."""
    return tag.rsplit(":", 1)[-1]


class _SvgChecker(HTMLParser):
    """A cheap look at an SVG file: nothing active, nothing external."""

    def __init__(self, policy: _UrlPolicy) -> None:
        super().__init__(convert_charrefs=True)
        self.policy = policy
        #: `xmlns:<prefix>` seen so far -> namespace URI.  Scopes are ignored:
        #: a prefix bound twice to different namespaces in one file is not
        #: something an honest picture does.
        self.namespaces: dict[str, str] = {}

    def _foreign_element(self, tag: str) -> str | None:
        """Message when the element is not SVG, judged by its namespace.

        The prefix alone means nothing (`<x:div xmlns:x="…/xhtml">` is HTML),
        so the declared namespace decides; an undeclared prefix is read by its
        spelling and, when that says nothing either, refused all the same -
        whatever namespace it turns out to be, it is not described here.
        """
        if ":" not in tag:
            return None
        prefix = tag.rsplit(":", 1)[0].lower()
        uri = self.namespaces.get(prefix, "").strip().rstrip("/")
        if uri == _XHTML_NAMESPACE or (not uri and prefix in _SVG_HTML_PREFIXES):
            return f"<{tag}>: HTML elements are not allowed in SVG files"
        if uri in (_SVG_NAMESPACE, _XLINK_NAMESPACE):
            return None
        if not uri and prefix in _SVG_OWN_PREFIXES:
            return None
        return f"<{tag}>: elements of another namespace are not allowed in SVG files"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        problem = self.policy.problem
        local = _local_name(tag)
        values = {name: value or "" for name, value in attrs}
        for name, value in values.items():
            if name.startswith("xmlns:") and len(name) > 6:
                self.namespaces[name[6:].lower()] = value
        if local in ("script", "foreignobject", "style"):
            problem(line, f"<{tag}> is not allowed in SVG files")
        else:
            foreign = self._foreign_element(tag)
            if foreign:
                problem(line, foreign)
        if local in _SVG_ANIMATION_ELEMENTS and values.get(
            "attributename", ""
        ).strip().lower() in ("href", "xlink:href"):
            problem(line, f"<{tag}>: animating 'href' is not allowed")
        for name, value in values.items():
            if name.startswith("on") and len(name) > 2:
                problem(line, f"<{tag} {name}>: event handlers are not allowed")
            elif name in _SVG_REFUSED_ATTRIBUTES:
                problem(line, f"<{tag} {name}>: '{name}' is not allowed in SVG files")
            elif name in _SVG_URL_ATTRIBUTES:
                kind, url = _classify_url(value)
                if kind in ("external", "script", "malformed"):
                    problem(line, f"<{tag} {name}>: external URL '{_show_url(url)}' is not allowed")
            elif name == "style" or "(" in value or "\\" in value:
                # `style` and the presentation attributes (fill="url(…)") are CSS
                check_css(value, self.policy, f"<{tag} {name}>", line)


def check_svg(
    text: str,
    exists: Callable[[str], bool] | None = None,
    is_dir: Callable[[str], bool] | None = None,
    base: str = "",
    base_path: str = DEFAULT_BASE_PATH,
) -> list[tuple[int, str]]:
    """Problems of one SVG file as (line, message) pairs.

    Not allowed: scripts, `<style>` elements, event handlers, `<foreignObject>`,
    elements of the XHTML namespace, `<!ENTITY` declarations,
    `<?xml-stylesheet`, animation of `href`, `srcset` and `xml:base`, external
    references in `href` / `src` and in the CSS of `style` and presentation
    attributes.  Elements are recognised by their local name (`svg:script` is a
    script); namespace URIs in `xmlns` are not references.

    `exists`, `is_dir` and `base_path` describe the output as for
    `check_html`, `base` is the directory of the file; without `exists` local
    URLs are not looked up.
    """
    policy = _UrlPolicy(
        exists if exists is not None else (lambda _path: True), is_dir, base, base_path
    )
    for pattern, message in _SVG_UNSAFE_MARKUP:
        match = pattern.search(text)
        if match:
            policy.problem(text.count("\n", 0, match.start()) + 1, message)
    checker = _SvgChecker(policy)
    checker.feed(text)
    checker.close()
    return policy.problems


#: At most this many problems are listed (a problem that repeats on every page
#: is reported once).
MAX_REPORTED_PROBLEMS = 25


def _scan_output(root: Path) -> tuple[dict[str, int], list[str], list[str]]:
    """(files -> size, directories, problems) of an output tree; paths are
    relative and use '/' (in the problems as `_output_path` shows them).
    Symbolic links are reported, never followed."""
    files: dict[str, int] = {}
    directories: list[str] = []
    problems: list[str] = []

    def walk(directory: Path, prefix: str) -> None:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            relative = f"{prefix}{entry.name}"
            if entry.is_symlink():
                problems.append(
                    f"{_output_path(relative)}: symbolic links are not allowed in the output"
                )
            elif entry.is_dir(follow_symlinks=False):
                directories.append(relative)
                walk(Path(entry.path), f"{relative}/")
            elif entry.is_file(follow_symlinks=False):
                files[relative] = entry.stat(follow_symlinks=False).st_size
            else:
                problems.append(f"{_output_path(relative)}: not a regular file")

    walk(root, "")
    return files, directories, problems


def _check_output_tree(
    files: dict[str, int], directories: Sequence[str], pages: Iterable[str]
) -> list[str]:
    """Allow-list of the top of the output and of the directories of the pages.

    `pages` are the tokens of the pages: the top of the output holds
    `assets/` and one directory `<token>/` per page with `index.html` and
    nothing else.  Anywhere in the output dot-files, dot-directories and the
    types of `FORBIDDEN_OUTPUT_EXTENSIONS` are refused, and no file may be
    larger than `MAX_FILE_BYTES`; which files `assets/` holds is checked by
    the caller (`menu_tools._output.asset_problems`).  Paths are shown by
    `_output_path`.
    """
    problems: list[str] = []
    expected_dirs = set(pages)
    expected_pages = {f"{token}/{PAGE_FILE}" for token in expected_dirs}
    page_rule = f"only {PAGE_FILE} is allowed in the directory of a page"

    for relative in directories:
        parts = relative.split("/")
        shown = _output_path(relative)
        if parts[-1].startswith("."):
            problems.append(f"{shown}: dot-directories must not be published")
        elif len(parts) == 1:
            if relative != ASSETS_DIRNAME and relative not in expected_dirs:
                problems.append(
                    f"{shown}: unexpected directory at the top of the output (only "
                    f"{ASSETS_DIRNAME}/ and one directory per page are allowed)"
                )
        elif parts[0] != ASSETS_DIRNAME:
            problems.append(f"{shown}: unexpected directory ({page_rule})")

    for relative, size in files.items():
        parts = relative.split("/")
        name = parts[-1]
        extension = os.path.splitext(name)[1].lower()
        shown = _output_path(relative)
        if name.startswith("."):
            problems.append(f"{shown}: dot-files must not be published")
        elif extension in FORBIDDEN_OUTPUT_EXTENSIONS:
            problems.append(f"{shown}: '{extension}' files must not be published")
        elif len(parts) == 1:
            problems.append(
                f"{shown}: unexpected file at the top of the output (the build writes "
                f"the pages and {ASSETS_DIRNAME}/ only)"
            )
        elif parts[0] != ASSETS_DIRNAME:
            if relative not in expected_pages:
                problems.append(f"{shown}: unexpected file ({page_rule})")
        if size > MAX_FILE_BYTES:
            problems.append(
                f"{shown}: {format_size(size)} is larger than the limit of "
                f"{format_size(MAX_FILE_BYTES)} for a single file"
            )

    for relative in sorted(expected_pages):
        if relative not in files:
            problems.append(f"{_output_path(relative)}: missing from the output")
    return problems


def check_output(
    out_dir: Path | str, pages: Iterable[str], base_path: str = DEFAULT_BASE_PATH
) -> OutputStats:
    """Check a finished output directory; raises `OutputError` with every problem.

    * only the expected entries are present (see `_check_output_tree`:
      `pages` are the tokens), none of them larger than `MAX_FILE_BYTES`;
    * HTML: no template syntax or comments left, no external resources or
      links, no inline scripts or event handlers, no embedded documents;
      every local URL lies under `base_path`, the path the output is
      published under, and resolves to a file of the output (see
      `check_html`);
    * CSS: `url()` and `@import` point at local files that exist (relative
      URLs of a CSS file are resolved against that file, root-absolute ones
      must lie under `base_path`); no CSS escapes that could hide a URL;
    * SVG: no scripts, styles sheets, event handlers, `<foreignObject>`,
      entities or external references (see `check_svg`).

    Messages never quote page text, and the directories of the pages are
    shown as `…` (`_output_path`): they are named after the tokens.
    """
    pages = list(pages)
    root = Path(out_dir)
    try:
        files, directories, problems = _scan_output(root)
    except OSError as exc:
        raise BuildError(
            f"cannot read the output directory {display_path(root)}: {exc.strerror}"
        ) from None
    problems += _check_output_tree(files, directories, pages)

    # only the directories of the shared files may be named in a message: the
    # rest are the directories of the pages
    known_dirs = {
        relative
        for relative in directories
        if relative.split("/", 1)[0] == ASSETS_DIRNAME
    }
    # problem -> [(file as shown, line, file)], in order of appearance; the
    # shown names of the pages are all alike (`…/index.html`)
    found: dict[str, list[tuple[str, int, str]]] = {}
    for relative, size in files.items():
        extension = os.path.splitext(relative)[1].lower()
        if extension not in (".html", ".css", ".svg") or size > MAX_FILE_BYTES:
            continue
        shown = _output_path(relative)
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            problems.append(f"{shown}: not valid UTF-8 (at byte {exc.start})")
            continue
        except OSError as exc:
            raise BuildError(f"cannot read {shown}: {exc.strerror}") from None
        if extension == ".html":
            file_problems = check_html(text, files.__contains__, known_dirs.__contains__, base_path)
        elif extension == ".css":
            file_problems = check_stylesheet(
                text, files.__contains__, known_dirs.__contains__,
                posixpath.dirname(relative), base_path,
            )  # fmt: skip
        else:
            file_problems = check_svg(
                text, files.__contains__, known_dirs.__contains__,
                posixpath.dirname(relative), base_path,
            )  # fmt: skip
        for line, message in file_problems:
            found.setdefault(message, []).append((shown, line, relative))

    for message, places in found.items():
        first_file, first_line, _first = places[0]
        distinct = len({name for _shown, _line, name in places})
        if distinct == 1:
            problems.append(f"{first_file} line {first_line}: {message}")
        else:
            problems.append(
                f"{distinct} files: {message}; first: {first_file} line {first_line}"
            )

    if problems:
        hidden = len(problems) - MAX_REPORTED_PROBLEMS
        if hidden > 0:
            problems = problems[:MAX_REPORTED_PROBLEMS] + [
                f"… and {hidden} more problem(s) in the output"
            ]
        raise OutputError(problems)
    return OutputStats(files=len(files), size=sum(files.values()))


# --------------------------------------------------------------------------
# Output directory handling
# --------------------------------------------------------------------------


def display_path(path: Path | str) -> str:
    """Path for logs: relative to the working directory when possible.

    A path of one component gets `./` in front (`./dist`): every path a
    message shows has a separator, which tells it from the words around it
    (`redact_tokens`)."""
    path = Path(path)
    try:
        shown = str(path.absolute().relative_to(Path.cwd())) or "."
    except ValueError:
        return str(path)
    if shown != "." and os.sep not in shown and "/" not in shown:
        shown = os.path.join(os.curdir, shown)
    return shown


#: A run of the characters of a token (`redact_tokens`).
_TOKEN_RUN_RE = re.compile(r"[A-Za-z0-9_-]+")
#: A path in a message: a word with at least one separator in it.
_PATH_WORD_RE = re.compile(r"[^\s/\\]*(?:[/\\][^\s/\\]*)+")
#: What takes the place of a hidden name.
NAME_MASK = "…"


def redact_tokens(text: Any, tokens: Collection[str]) -> str:
    """`text` with the tokens of `tokens` (lower case) hidden in its paths.

    A path is a word of the message with a separator in it (`display_path`
    always gives one).  Inside it a whole run of token characters that is one
    of the tokens, in any letter case (on a file system that ignores it,
    `EVE-xxxx/` is the directory of `eve-xxxx`), becomes `…`: a component
    (`dist/<token>/`), or a name with a dot (`.<token>.tmp-…`,
    `<token>.zip`).  A token inside a longer name (`<token>_old`) is not a
    component and stays; the words of the message stay as they are, so the
    mask never tells that a token equals one of them.  Whatever path a
    message shows - `--out`, a temporary directory next to it, the file of
    an error - the directory of a page does not reveal its token."""
    text = str(text)
    if not tokens:
        return text

    def hide(path: re.Match) -> str:
        return _TOKEN_RUN_RE.sub(
            lambda run: NAME_MASK if run.group(0).lower() in tokens else run.group(0),
            path.group(0),
        )

    return _PATH_WORD_RE.sub(hide, text)


def _output_path(relative: str) -> str:
    """A path inside the output for a message.

    Every entry at the top of the output but `assets` is the directory of a
    page, named after its token, or something the build never writes: it is
    shown as `…`, unless its name has a dot (a token never has one).
    """
    top, sep, rest = relative.partition("/")
    if top != ASSETS_DIRNAME and "." not in top:
        top = NAME_MASK
    return f"{top}{sep}{rest}"


def _same_path(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return first == second


def _is_within(path: Path, ancestor: Path) -> bool:
    """True when `path` is `ancestor` or lies inside it (both already resolved)."""
    return any(_same_path(candidate, ancestor) for candidate in (path, *path.parents))


def check_out_dir(
    out_dir: Path | str,
    *,
    code_dir: Path | str,
    data_dir: Path | str,
) -> None:
    """Refuse output directories whose replacement would destroy anything.

    The build replaces `--out` completely, so it must not be the code or data
    directory (or a parent of one), the working directory (or a parent of
    it), the home directory, the file system root, or a directory inside the
    tree that is copied into the output (`assets/` of the code).  An existing
    directory is replaced only when it is empty or looks like the output of a
    previous build.

    The messages call the directory `--out` and never repeat its path nor
    the name of anything in it: it may point inside a previous build by
    mistake, at the directory of a page, and the data is not read yet, so no
    token is known to hide.  An error of the file system is reported by its
    reason alone, without the file it happened on.
    """
    try:
        _check_out_dir(Path(out_dir), Path(code_dir), Path(data_dir))
    except OSError as exc:
        raise BuildError(
            f"cannot inspect --out: {exc.strerror or type(exc).__name__}"
        ) from None


def _check_out_dir(out_dir: Path, code_dir: Path, data_dir: Path) -> None:
    out = Path(out_dir).absolute()
    resolved = Path(os.path.realpath(out))

    if resolved == Path(resolved.anchor):
        raise BuildError("--out must not be the file system root")
    try:
        home = Path(os.path.realpath(Path.home()))
    except (RuntimeError, OSError):  # pragma: no cover - home is normally defined
        home = None
    if home is not None and _same_path(resolved, home):
        raise BuildError("--out must not be the home directory")
    if out.exists() and not out.is_dir():
        raise BuildError("--out exists and is not a directory")

    protected = {
        "code": Path(code_dir),
        "data": Path(data_dir),
        "working": Path.cwd(),
    }
    for label, path in protected.items():
        target = Path(os.path.realpath(path.absolute()))
        for candidate in (target, *target.parents):
            if _same_path(resolved, candidate):
                relation = "the" if candidate == target else "a parent of the"
                raise BuildError(
                    f"--out must not be {relation} {label} directory; "
                    "choose a separate output directory"
                )

    assets = Path(os.path.realpath((Path(code_dir) / ASSETS_DIRNAME).absolute()))
    if _is_within(resolved, assets):
        relation = "the" if _same_path(resolved, assets) else "inside the"
        raise BuildError(
            f"--out must not be {relation} assets directory; "
            "choose a separate output directory"
        )

    if out.is_symlink():
        raise BuildError("--out must not be a symbolic link; point --out at the real directory")
    check_replaceable(out)


def _directory_entries(path: str) -> dict[str, os.DirEntry] | None:
    """The entries of a directory but the files of the operating system;
    None when it cannot be read."""
    try:
        with os.scandir(path) as iterator:
            return {entry.name: entry for entry in iterator if entry.name not in OS_JUNK_FILES}
    except OSError:
        return None


def _is_page_directory(entry: os.DirEntry) -> bool:
    """A real directory that holds `index.html` (a regular file) and nothing else."""
    if not entry.is_dir(follow_symlinks=False):
        return False
    inside = _directory_entries(entry.path)
    return (
        inside is not None
        and list(inside) == [PAGE_FILE]
        and inside[PAGE_FILE].is_file(follow_symlinks=False)
    )


#: What every build writes into `assets/`: a previous build has them.
BUILD_MARKER_ASSETS = ("app.css", "app.js")


def _is_built_assets(entry: os.DirEntry) -> bool:
    """`assets/` as a build writes it: a real directory with `app.css` and
    `app.js` as regular files."""
    if not entry.is_dir(follow_symlinks=False):
        return False
    inside = _directory_entries(entry.path)
    return inside is not None and all(
        name in inside and inside[name].is_file(follow_symlinks=False)
        for name in BUILD_MARKER_ASSETS
    )


def _count_entries(entries: Sequence[os.DirEntry]) -> str:
    """`2 directories and 1 other entry`: what is there, without a name."""
    directories = sum(1 for entry in entries if entry.is_dir(follow_symlinks=False))
    others = len(entries) - directories
    parts = []
    if directories:
        parts.append(f"{directories} director{'y' if directories == 1 else 'ies'}")
    if others:
        parts.append(f"{others} other entr{'y' if others == 1 else 'ies'}")
    return " and ".join(parts)


def check_replaceable(out_dir: Path | str) -> None:
    """Allow replacing an existing directory only if it is a previous build.

    A directory qualifies when it is empty or holds what a build writes:
    `assets/`, a real directory with `app.css` and `app.js` (every build
    writes them), and the directories of the pages - real directories named
    like a token with `index.html` (a regular file) alone; nothing else
    (files created by the operating system are ignored).  No marker file is
    written into the output: its contents stay limited to what the pages
    need.  Anything else is somebody's directory and is never replaced:
    pages without `assets/`, `assets/` without `app.css` and `app.js`, any
    other entry at the top, the directory of a single page.

    The messages never repeat the path of `--out` nor the name of anything
    in it - at most they count the entries: the data is not read yet, so no
    token is known, and `--out` may hold the pages of a previous build.  An
    error of the file system names no file either.
    """
    try:
        _check_replaceable(Path(out_dir))
    except OSError as exc:
        raise BuildError(
            f"cannot inspect --out: {exc.strerror or type(exc).__name__}"
        ) from None


def _check_replaceable(out: Path) -> None:
    try:
        with os.scandir(out) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise BuildError(f"cannot read --out: {exc.strerror}") from None
    entries = [entry for entry in entries if entry.name not in OS_JUNK_FILES]
    if not entries:
        return
    refuse = "refusing to replace --out"
    advice = "remove it manually or choose another --out"
    names = [entry.name for entry in entries]
    if names == [PAGE_FILE]:
        raise BuildError(
            f"{refuse}: it holds {PAGE_FILE} alone, like the directory of one page; point "
            f"--out at the directory with the pages and {ASSETS_DIRNAME}/"
        )
    others = [entry for entry in entries if entry.name != ASSETS_DIRNAME]
    unexpected = [
        entry
        for entry in others
        if data_tools.check_token(entry.name) is not None or not _is_page_directory(entry)
    ]
    if unexpected:
        raise BuildError(
            f"{refuse}: it does not look like a previous build output (unexpected at the "
            f"top: {_count_entries(unexpected)}; their names are not shown, they may be "
            f"tokens); {advice}"
        )
    assets = next((entry for entry in entries if entry.name == ASSETS_DIRNAME), None)
    if assets is None or not _is_built_assets(assets):
        raise BuildError(
            f"{refuse}: it does not look like a previous build output (no {ASSETS_DIRNAME}/ "
            f"with {' and '.join(BUILD_MARKER_ASSETS)}, which every build writes; the pages "
            f"alone are not replaced either); {advice}"
        )


def _remove_tree(path: Path) -> bool:
    """Remove a directory tree (or a symlink); True when nothing is left."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass
    return not os.path.lexists(path)


class _StagedOutput:
    """Build into a temporary directory next to `--out`, then swap it in.

    The temporary names are `.<name>.tmp-<hex>` (the new output) and
    `.<name>.old-<hex>` (the previous one while it is being replaced).  They
    may hold rendered pages, so leftovers of an interrupted build are removed
    before the next one starts, and a failure to remove them is reported.
    """

    def __init__(self, out_dir: Path, warn: Callable[[str], None]):
        self.out = Path(out_dir).absolute()
        self.warn = warn
        self.stage = self.out.parent / f".{self.out.name}.tmp-{secrets.token_hex(6)}"
        self._stale_re = re.compile(
            rf"\.{re.escape(self.out.name)}\.(?:tmp|old)-[0-9a-f]{{12}}\Z"
        )

    def __enter__(self) -> Path:
        try:
            self.out.parent.mkdir(parents=True, exist_ok=True)
            self._remove_stale()
            self.stage.mkdir()
        except OSError as exc:
            raise BuildError(
                f"cannot create a temporary directory next to --out: {exc.strerror}"
            ) from None
        return self.stage

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self._discard(self.stage)
            return False
        self._swap()
        return False

    def _remove_stale(self) -> None:
        """Remove what an interrupted build left next to the output directory."""
        with os.scandir(self.out.parent) as entries:
            stale = [Path(entry.path) for entry in entries if self._stale_re.match(entry.name)]
        for path in stale:
            self._discard(path)

    def _discard(self, path: Path) -> None:
        if not _remove_tree(path):
            self.warn(
                f"could not remove the temporary directory {display_path(path)}; "
                "it may contain rendered pages, remove it manually"
            )

    def _swap(self) -> None:
        previous = self.out.parent / f".{self.out.name}.old-{secrets.token_hex(6)}"
        try:
            if os.path.lexists(self.out):
                os.rename(self.out, previous)
            os.rename(self.stage, self.out)
        except OSError as exc:
            hint = ""
            if os.path.lexists(previous) and not os.path.lexists(self.out):
                try:  # put the previous output back
                    os.rename(previous, self.out)
                except OSError:
                    hint = f"; the previous output was kept in {display_path(previous)}"
            self._discard(self.stage)
            raise BuildError(
                f"cannot replace the output directory (--out): {exc.strerror}{hint}"
            ) from None
        if os.path.lexists(previous):
            self._discard(previous)


def copy_assets(source: Path, destination: Path) -> int:
    """Copy `assets/` into the output; returns the number of files.

    Dot-files and dot-directories are skipped.  Symbolic links are an error
    (they are never followed), and directories that end up empty are not
    created.
    """
    source = Path(source)
    if source.is_symlink():
        raise BuildError(
            f"the assets directory must not be a symbolic link: {display_path(source)}"
        )
    if not source.is_dir():
        raise BuildError(f"assets directory not found: {display_path(source)}")

    def skip(directory: str, names: list[str]) -> set[str]:
        skipped: set[str] = set()
        for name in names:
            path = os.path.join(directory, name)
            if name.startswith("."):
                skipped.add(name)
                continue
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                raise BuildError(
                    f"symbolic links are not allowed in assets: {display_path(path)}"
                )
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise BuildError(f"not a regular file in assets: {display_path(path)}")
        return skipped

    shown = display_path(source)
    try:
        shutil.copytree(source, destination, ignore=skip)
        for directory, _dirs, _files in os.walk(destination, topdown=False):
            if Path(directory) != Path(destination) and not os.listdir(directory):
                os.rmdir(directory)
    except shutil.Error as exc:  # a list of (source, destination, reason)
        failures = exc.args[0] if exc.args and isinstance(exc.args[0], list) else []
        detail = f"{len(failures)} file(s) could not be copied"
        if failures:
            failed, _target, reason = failures[0]
            detail += f"; first: {display_path(failed)}: {reason}"
        raise BuildError(f"cannot copy assets from {shown}: {detail}") from None
    except OSError as exc:
        where = f" ({display_path(exc.filename)})" if exc.filename else ""
        raise BuildError(
            f"cannot copy assets from {shown}: {exc.strerror or type(exc).__name__}{where}"
        ) from None
    return sum(len(files) for _root, _dirs, files in os.walk(destination))


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def _read_source(path: Path, what: str) -> str:
    if path.is_symlink():
        raise BuildError(
            f"the {what} must not be a symbolic link: {display_path(path)}"
        )
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise BuildError(f"{what} not found: {display_path(path)}") from None
    except UnicodeDecodeError as exc:
        raise BuildError(
            f"{display_path(path)}: not valid UTF-8 (at byte {exc.start})"
        ) from None
    except OSError as exc:
        raise BuildError(
            f"cannot read the {what} {display_path(path)}: {exc.strerror}"
        ) from None


def load_fragments(directory: Path) -> Fragments:
    """Read and parse every fragment below `directory` (`fragments/`).

    A missing directory means that there are no fragments.  Dot-files and
    dot-directories are skipped; symbolic links, other kinds of files and any
    extension but `.html` are an error.  Nothing is read after this.
    """
    directory = Path(directory)
    if directory.is_symlink():
        raise BuildError(
            f"the fragments directory must not be a symbolic link: {display_path(directory)}"
        )
    if not directory.exists():
        return Fragments()
    if not directory.is_dir():
        raise BuildError(f"not a directory: {display_path(directory)}")
    sources: dict[str, str] = {}
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError as exc:
            raise BuildError(
                f"cannot read the fragments directory {display_path(current)}: {exc.strerror}"
            ) from None
        for path in entries:
            if path.name.startswith("."):
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise BuildError(
                    f"symbolic links are not allowed in fragments: {display_path(path)}"
                )
            if stat.S_ISDIR(mode):
                pending.append(path)
                continue
            if not stat.S_ISREG(mode):
                raise BuildError(f"not a regular file in fragments: {display_path(path)}")
            relative = path.relative_to(directory).as_posix()
            if path.suffix != FRAGMENT_SUFFIX:
                raise BuildError(
                    f"{FRAGMENTS_DIRNAME}/{relative}: only {FRAGMENT_SUFFIX} files "
                    "are allowed in fragments"
                )
            sources[relative[: -len(FRAGMENT_SUFFIX)]] = _read_source(path, "fragment")
    return Fragments(sources)


def load_template(path: Path) -> Template:
    """Read and parse the page template with the fragments next to it."""
    fragments = load_fragments(path.parent / FRAGMENTS_DIRNAME)
    return parse_template(_read_source(path, "template"), path.name, fragments)


def write_pages(stage: Path, pages: Iterable[tuple[str, str]]) -> int:
    """Write `<token>/index.html` for every rendered page."""
    count = 0
    for token, page in pages:
        path = stage / token / PAGE_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(page)
        except OSError as exc:
            raise BuildError(f"cannot write a page: {exc.strerror}") from None
        count += 1
    return count


# --------------------------------------------------------------------------
# Command line interface
# --------------------------------------------------------------------------


def base_path_argument(value: str) -> str:
    """`build --base-path`: a bad value is a bad command line (code 2)."""
    try:
        return check_base_path(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def token_prefix(value: str) -> str:
    """`token --prefix NAME`: the characters of a token; the value is not
    repeated in the message."""
    problem = check_token_prefix(value)
    if problem:
        raise argparse.ArgumentTypeError(problem)
    return value


#: Environment variables that mark an automated run; `links` refuses to work
#: there, because it is the one command that prints personal data.
CI_ENVIRONMENT_VARIABLES = ("CI", "GITHUB_ACTIONS")


def running_in_ci() -> bool:
    """True when `CI` or `GITHUB_ACTIONS` is set (and is not empty, 0 or false)."""
    return any(
        os.environ.get(name, "").strip().lower() not in ("", "0", "false")
        for name in CI_ENVIRONMENT_VARIABLES
    )


#: '%40' is '@', '%3A' is ':' - both would pass urlsplit as part of the host.
_PERCENT_CREDENTIALS_RE = re.compile(r"%(?:40|3a)", re.IGNORECASE)


def parse_published_url(value: str) -> str:
    """`links --url`: the http(s) address where the output directory is
    published (the address of the site and `--base-path` of the build); the
    trailing '/' is dropped."""
    value = value.strip()
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        parts = None
    if (
        parts is None
        or parts.scheme.lower() not in ("http", "https")
        or not parts.hostname
        or parts.username  # credentials in the URL would end up in the pages
        or parts.password
        or "@" in parts.netloc
        # percent-encoded '@' and ':' hide credentials from urlsplit, and the
        # address would silently build broken links
        or _PERCENT_CREDENTIALS_RE.search(parts.netloc)
        or parts.query
        or parts.fragment
        or "?" in value
        or "#" in value
        or any(char.isspace() for char in value)
    ):
        # the value itself is never repeated: it may carry credentials
        raise argparse.ArgumentTypeError(
            "expected the address where the output directory is published, e.g. "
            "https://example.org/menu (http or https, no user information, query "
            "string or fragment)"
        )
    return value.rstrip("/")
