"""Checks of the menu builder's finished output.

`check_output` (from `_engine`) runs first: the top level of the output
holds a `<token>/` directory with `index.html` for every page, `assets/`,
and nothing else.  Every local address on a page, link or resource, must
lie under the base path and name a file in the output: a page that leads
elsewhere on the site is an error.

This module adds four rules:

- `assets/` holds `app.css`, `app.js` and `favicon.svg` and nothing else
  (any other published file from the code, a font or a note, is a problem);
- no element carries a `style` attribute, inside an inline SVG too: the
  styles live in `assets/app.css` alone (`check_output` looks at the URLs
  in a `style` attribute, not at the attribute itself);
- a page links only to its own parts: every `<a>` and `<area>` has an
  `href` of the form `#<id>` naming an element on the same page
  (`check_output` lets a fragment pass without looking at its target, and a
  link to another page in the output would resolve);
- no file holds a record's token, in any letter case, its own page
  included: a token is only the name of its page's directory.

All problems are reported in one `OutputError`, at most
`MAX_REPORTED_PROBLEMS` lines, the way `check_output` reports them.  The
messages never quote page text or a token, and page directories are shown
as `…`, since they are named after the tokens.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping

from menu_tools import _core
from menu_tools._schema import guest_where

#: The directory of the files the pages share, at the top of the output.
ASSETS_DIR = "assets"
#: Everything `assets/` of the output holds.
ASSET_FILES = ("app.css", "app.js", "favicon.svg")

STYLE_PROBLEM = "the attribute 'style' is not allowed (the styles live in assets/app.css)"
ASSETS_RULE = f"only {', '.join(ASSET_FILES[:-1])} and {ASSET_FILES[-1]} are published in {ASSETS_DIR}/"
TOKEN_RULE = "a token is only the name of its page directory"
#: The elements whose `href` is a link a reader follows.
LINK_TAGS = ("a", "area")
#: A link with no `href`, or one that is not a fragment of the page.
LINK_RULE = "must lead to a part of the same page ('#' and the id of an element on it)"
#: A fragment that is empty or names no id of the page.
LINK_TARGET_PROBLEM = "names no element of the page"

#: The last line of a list of problems that was cut short.
_MORE_RE = re.compile(r"… and (\d+) more problem\(s\) in the output\Z")


class _StyleFinder(HTMLParser):
    """Collects the lines of the elements with a `style` attribute."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.lines: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # the parser gives the names of the attributes in lower case
        if any(name == "style" for name, _value in attrs):
            self.lines.append(self.getpos()[0])


def style_lines(document: str) -> list[int]:
    """The lines of the elements of an HTML document that have a `style`
    attribute (of any element, the elements of an inline SVG included)."""
    finder = _StyleFinder()
    finder.feed(document)
    finder.close()
    return finder.lines


class _LinkFinder(HTMLParser):
    """Collects the ids of a document and its links: (line, tag, href) of
    every `<a>` and `<area>`, href None when the element has none."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[tuple[int, str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # a browser takes the first of two attributes of the same name
        first: dict[str, str] = {}
        for name, value in attrs:
            first.setdefault(name, value or "")
        if first.get("id"):
            self.ids.add(first["id"])
        if tag in LINK_TAGS:
            self.links.append((self.getpos()[0], tag, first.get("href")))


def link_lines(document: str) -> list[tuple[int, str]]:
    """(line, problem) of every link of an HTML document that does not lead
    to an element of the document itself: an `<a>` or `<area>` without an
    `href` or with one that is not `#<id>` (`<a href> must lead to ...`), or
    with a fragment that is empty or names no id of the document
    (`<a href> names no element of the page`).  An id may stand anywhere in
    the document, before or after the link."""
    finder = _LinkFinder()
    finder.feed(document)
    finder.close()
    problems = []
    for line, tag, href in finder.links:
        if href is None or not href.startswith("#"):
            problems.append((line, f"<{tag} href> {LINK_RULE}"))
        elif href[1:] not in finder.ids:
            problems.append((line, f"<{tag} href> {LINK_TARGET_PROBLEM}"))
    return problems


def shown_path(relative: str) -> str:
    """A path inside the output for a message: the directory of a page (any
    entry at the top but `assets` without a dot in its name) is `…`."""
    top, separator, rest = relative.partition("/")
    if top != ASSETS_DIR and "." not in top:
        top = _core.NAME_MASK
    return f"{top}{separator}{rest}"


def _files(root: Path, suffix: str = "") -> list[str]:
    """The files below `root` whose names end in `suffix` (letter case
    aside), as sorted relative '/' paths; symbolic links are never followed
    (`check_output` reports them).  A directory that cannot be read raises
    `BuildError`."""
    found: list[str] = []

    def walk(directory: Path, prefix: str) -> None:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            relative = f"{prefix}{entry.name}"
            if entry.is_dir(follow_symlinks=False):
                walk(Path(entry.path), f"{relative}/")
            elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(suffix):
                found.append(relative)

    try:
        walk(root, "")
    except OSError as exc:
        raise _core.BuildError(
            f"cannot read the output directory {_core.display_path(root)}: {exc.strerror}"
        ) from None
    return found


def style_problems(out_dir: Path | str) -> list[str]:
    """The `style` attributes of the HTML files of an output directory, one
    line per file, or one line for every file at once:
    `3 files: <problem>; first: …/index.html line 12`."""
    root = Path(out_dir)
    places: list[tuple[str, int]] = []
    files = _files(root, ".html")
    for relative in files:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # `check_output` reports it
        except OSError as exc:
            raise _core.BuildError(f"cannot read {shown_path(relative)}: {exc.strerror}") from None
        lines = style_lines(text)
        if lines:
            places.append((shown_path(relative), lines[0]))
    if not places:
        return []
    first, line = places[0]
    if len(places) == 1:
        return [f"{first} line {line}: {STYLE_PROBLEM}"]
    return [f"{len(places)} files: {STYLE_PROBLEM}; first: {first} line {line}"]


def link_problems(out_dir: Path | str) -> list[str]:
    """The links of the HTML files of an output directory that do not lead
    to a part of their own page (`link_lines`), a line per problem and file
    (its first place there), or one line for every file with the same
    problem: `3 files: <problem>; first: …/index.html line 12`.  Neither the
    address nor the text of a page is shown."""
    root = Path(out_dir)
    places: dict[str, list[tuple[str, int]]] = {}
    for relative in _files(root, ".html"):
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # `check_output` reports it
        except OSError as exc:
            raise _core.BuildError(f"cannot read {shown_path(relative)}: {exc.strerror}") from None
        seen: set[str] = set()
        for line, problem in link_lines(text):
            if problem not in seen:
                seen.add(problem)
                places.setdefault(problem, []).append((shown_path(relative), line))
    problems = []
    for problem, found in places.items():
        first, line = found[0]
        if len(found) == 1:
            problems.append(f"{first} line {line}: {problem}")
        else:
            problems.append(f"{len(found)} files: {problem}; first: {first} line {line}")
    return problems


def asset_problems(out_dir: Path | str) -> list[str]:
    """What `assets/` of an output directory holds besides `ASSET_FILES`,
    a line per entry at its top (a directory with a trailing '/').  The
    names are shown: they are the names of files of the code."""
    root = Path(out_dir) / ASSETS_DIR
    try:
        with os.scandir(root) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except FileNotFoundError:
        return []  # the pages refer to its files: `check_output` reports them missing
    except OSError as exc:
        raise _core.BuildError(f"cannot read {ASSETS_DIR}/ of the output: {exc.strerror}") from None
    problems: list[str] = []
    for entry in entries:
        if entry.name in ASSET_FILES and entry.is_file(follow_symlinks=False):
            continue
        if entry.is_dir(follow_symlinks=False):
            problems.append(f"{ASSETS_DIR}/{entry.name}/: unexpected directory ({ASSETS_RULE})")
        else:
            problems.append(f"{ASSETS_DIR}/{entry.name}: unexpected file ({ASSETS_RULE})")
    return problems


def token_problems(
    out_dir: Path | str, pages: Iterable[str], numbers: Mapping[str, int] | None = None
) -> list[str]:
    """The files of an output directory that hold the token of a page (any
    letter case), a line per record that names it by its number and never
    shows the token:
    `guests.json: guest #2: its token is in …/index.html; <rule>` or
    `guests.json: guest #2: its token is in 3 files of the output, first: assets/app.css; <rule>`.

    `numbers` gives the number of the record of each token in `guests.json`;
    without it a record is numbered by the position of its token in `pages`,
    from 1.  The names of the directories are not looked at: they are the
    tokens.
    """
    root = Path(out_dir)
    tokens = list(pages)
    if numbers is None:
        numbers = {token: position for position, token in enumerate(tokens, start=1)}
    found: dict[str, list[str]] = {}
    for relative in _files(root):
        try:
            # the tokens are ASCII: lower case bytes compare them in any letter case
            text = (root / relative).read_bytes().lower()
        except OSError as exc:
            raise _core.BuildError(f"cannot read {shown_path(relative)}: {exc.strerror}") from None
        for token in tokens:
            if token.lower().encode("utf-8") in text:
                found.setdefault(token, []).append(shown_path(relative))
    problems = []
    for token in sorted(found, key=lambda token: numbers[token]):
        places = found[token]
        where = places[0] if len(places) == 1 else f"{len(places)} files of the output, first: {places[0]}"
        problems.append(f"{guest_where(numbers[token])}: its token is in {where}; {TOKEN_RULE}")
    return problems


def _limited(problems: list[str], hidden: int) -> list[str]:
    """At most `MAX_REPORTED_PROBLEMS` lines and a count of the others."""
    limit = _core.MAX_REPORTED_PROBLEMS
    hidden += max(0, len(problems) - limit)
    problems = problems[:limit]
    if hidden:
        problems.append(f"… and {hidden} more problem(s) in the output")
    return problems


def check_menu_output(
    out_dir: Path | str, pages: Iterable[str], *, base_path: str, numbers: Mapping[str, int] | None = None
) -> "_core.OutputStats":
    """Check a finished output directory of the menu published under
    `base_path`; `pages` are the tokens of every page (the guests and the
    staff), `numbers` the numbers of their records in `guests.json` for the
    messages (see `token_problems`).

    `check_output` first, then the files in `assets/`, the `style`
    attributes, the links on the pages and the tokens in the files; all
    problems together raise one `OutputError`.
    """
    pages = list(pages)
    problems: list[str] = []
    hidden = 0
    stats = None
    try:
        stats = _core.check_output(out_dir, pages, base_path=base_path)
    except _core.OutputError as exc:
        problems = list(exc.errors)
        more = _MORE_RE.match(problems[-1]) if problems else None
        if more:
            hidden = int(more.group(1))
            problems.pop()
    problems += asset_problems(out_dir)
    problems += style_problems(out_dir)
    problems += link_problems(out_dir)
    problems += token_problems(out_dir, pages, numbers)
    if problems or stats is None:
        raise _core.OutputError(_limited(problems, hidden))
    return stats


__all__ = [
    "ASSET_FILES",
    "ASSETS_RULE",
    "LINK_RULE",
    "LINK_TARGET_PROBLEM",
    "STYLE_PROBLEM",
    "TOKEN_RULE",
    "asset_problems",
    "check_menu_output",
    "link_lines",
    "link_problems",
    "shown_path",
    "style_lines",
    "style_problems",
    "token_problems",
]
