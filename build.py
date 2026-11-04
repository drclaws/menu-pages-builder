#!/usr/bin/env python3
"""Builder of personal dinner-menu pages.

    python build.py build    [--data DIR] [--out DIR] [--base-path PATH]
    python build.py validate [--data DIR]
    python build.py links    --url URL [--data DIR]
    python build.py token    [--prefix NAME]

The builder writes a page per guest and a staff page for the restaurant, each
at a secret address `<base path>/<token>/`.  Only the Python 3 standard library
is used (Python >= 3.10).

`validate` reads `menu.json` and `guests.json` in DIR (by default
`examples/data` next to this script), checks them, builds the page trees in
memory (that is how it learns what the pages show) and prints a summary.

`build` does the same and renders every page with `template.html` and its
fragments, then writes the output: `<token>/index.html` for every guest record
and for the staff record, and `assets/` with the style sheet and the script of
the code and `favicon.svg`, generated from the design tokens of
`assets/app.css` - nothing else.  The output is assembled next to `--out`
(`dist` in the current directory by default) and replaces it only when every
check has passed: nothing but the expected files, no external resources, no
inline scripts or styles, every local URL resolves inside the output, and no
file holds the token of a record (a token is only the name of the directory
of its page).  Its
contents are published under `--base-path` (`/` by default): every URL of the
output starts with it, and a local address outside it is an error - the pages
lead nowhere else on the site.  Two builds of the same data are identical
byte for byte.

`links` checks the data as `validate` does and prints the address of every
page, `URL/<token>/` after the name of its guest record and a tab, the staff
page last after `staff`; it prints personal data, so it is meant for local
use only and refuses to run in CI.  `token` prints a new token: fully random
(as the staff record needs it) or `NAME-xxxx`, readable with a random tail.

Warnings and errors go to stderr; they never quote the data, and a token that
is part of a path in a message is hidden.  A message about a record names it
`guests.json: guest #N`, N being its position in `guests.json` (the staff
record counts too).

Importing this module has no side effects: everything happens inside `main()`.

Exit codes: 0 - success (`--help`, valid data, a finished build, the links,
a token), 1 - errors in the data or in the finished output, an output
directory that is not replaced, `links` in CI, 2 - bad command line.
"""

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Any, NamedTuple

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

#: The directory of this script; the default data directory is relative to it.
CODE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path("examples") / "data"
#: Relative to the current working directory.
DEFAULT_OUT_DIR = Path("dist")
DEFAULT_BASE_PATH = "/"

TEMPLATE_FILE = "template.html"
#: The files the pages share, in the code and in the output.
ASSETS_DIR = "assets"
#: The style sheet whose design tokens colour the pages and the icon.
TOKENS_FILE = "app.css"
#: The icon the build writes into `assets/` of the output.
FAVICON_FILE = "favicon.svg"

#: The commands and their one-line descriptions.
COMMANDS = {
    "build": "build the pages of the guests and the staff page",
    "validate": "check the data without writing anything",
    "links": "print the address of every page (personal data: for local use only)",
    "token": "print a new token for a record",
}


def _base_path_type(value: str) -> str:
    """`build --base-path`: the rule of the invitations (a bad value is a bad
    command line, and it is not repeated)."""
    from menu_tools import _core

    return _core.base_path_argument(value)


def _url_type(value: str) -> str:
    """`links --url`: an http(s) address without credentials, query or
    fragment; the trailing '/' is dropped (the rule of the invitations)."""
    from menu_tools import _core

    return _core.parse_published_url(value)


def _prefix_type(value: str) -> str:
    """`token --prefix`: the characters of a token (the rule of the invitations)."""
    from menu_tools import _core

    return _core.token_prefix(value)


def make_parser() -> argparse.ArgumentParser:
    """The command line parser: a required subcommand."""
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description="Builder of personal dinner-menu pages.",
    )
    commands = parser.add_subparsers(dest="command", metavar="command", required=True)

    def add_data_option(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--data",
            metavar="DIR",
            help=f"data directory with menu.json and guests.json (default: {DEFAULT_DATA_DIR} next to build.py)",
        )

    build = commands.add_parser("build", help=COMMANDS["build"], description=COMMANDS["build"])
    add_data_option(build)
    build.add_argument(
        "--out",
        metavar="DIR",
        help="output directory: <token>/index.html for every page and assets/, nothing else; "
        f"replaced on every build (default: {DEFAULT_OUT_DIR})",
    )
    build.add_argument(
        "--base-path",
        metavar="PATH",
        type=_base_path_type,
        help="path from the root of the site under which the contents of --out are published, "
        "e.g. /menu: every URL of the output starts with it, a page is PATH/<token>/ and a "
        f"local address outside PATH is an error (default: {DEFAULT_BASE_PATH})",
    )

    validate = commands.add_parser("validate", help=COMMANDS["validate"], description=COMMANDS["validate"])
    add_data_option(validate)

    links = commands.add_parser(
        "links",
        help=COMMANDS["links"],
        description="Print the address of every page for sending by hand: the name of each guest "
        "record, a tab and URL/<token>/, the staff page last. The lines hold personal data and the "
        "secret addresses: the command is for local use only and refuses to run in CI.",
    )
    links.add_argument(
        "--url",
        metavar="URL",
        required=True,
        type=_url_type,
        help="address where the output directory of the build is published, e.g. "
        "https://example.org/menu; the links are URL/<token>/",
    )
    add_data_option(links)

    token = commands.add_parser("token", help=COMMANDS["token"], description=COMMANDS["token"])
    token.add_argument(
        "--prefix",
        metavar="NAME",
        type=_prefix_type,
        help="print a readable token NAME-xxxx with a short random tail (NAME: A-Z, a-z, 0-9, '_' "
        "and '-'); without it the token is fully random, as the staff record needs it",
    )
    return parser


class Data(NamedTuple):
    """Checked data and the trees of its pages."""

    menu: dict
    guests: list
    #: What the checks learned (`menu_tools._schema.MenuIndex`).
    index: Any
    #: The page trees (`menu_tools._page.Trees`).
    trees: Any


def load_data(data_dir: Path | str, report: Any, settings: Any = None) -> Data:
    """Read and check `menu.json` and `guests.json` in `data_dir`, then build
    the page trees once.

    The order matters: `menu.json` first, because the keys of `guests.json`
    are shown in messages only when they are field names of the format or ids
    declared in `menu.json`; then the records; then the trees, which report a
    table plan that does not fit and tell what the pages show.  All errors
    are collected and raised together as a `ValidationError` (warnings go to
    the report as they come).
    """
    from menu_tools import _core, _page, _schema

    path = Path(data_dir)
    if not path.is_dir():
        report.error(f"data directory not found: {_core.display_path(path)}")
        report.raise_if_failed()
    menu = _core.read_json(path / _schema.MENU_FILE, report)
    index = _schema.check_menu(menu, report) if menu is not _core.MISSING else _schema.MenuIndex()
    guests = _core.read_json(path / _schema.GUESTS_FILE, report, _schema.guest_known(index))
    report.remember_tokens(guests)
    if guests is not _core.MISSING and index.version_ok:
        _schema.check_guests(guests, index, menu, report)
    report.raise_if_failed()
    trees = _page.build_trees(menu, guests, report, settings or _page.DEFAULT_SETTINGS)
    report.raise_if_failed()
    _schema.check_usage(index, menu, trees.usage, report)
    return Data(menu, guests, index, trees)


def summary(data: Data) -> str:
    """`validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), ...`"""
    index = data.index
    staff = " + staff" if data.trees.staff is not None else ""
    return (
        f"validate: OK - {index.seats} seat(s), {index.guests} guest record(s){staff}, "
        f"{len(index.dishes)} dish(es), {len(index.sets)} set(s), {len(index.drinks)} drink(s)"
    )


def pages_of(data: Data) -> list:
    """Every page (`menu_tools._page.Page`): the guests in the order of
    `guests.json`, then the staff page, if any."""
    staff = [data.trees.staff] if data.trees.staff is not None else []
    return [*data.trees.guests, *staff]


def _stdout(message: str) -> None:
    # Flushed on every line so that stdout and stderr stay in order in CI logs.
    print(message, flush=True)


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def cli_report() -> Any:
    """The report of a command: warnings go to stderr at once, with the
    tokens it has seen hidden (`Report.redact`)."""
    from menu_tools import _core

    def warn(message: str) -> None:
        _stderr(f"warning: {report.redact(message)}")

    report = _core.Report(on_warn=warn)
    return report


def _data_dir(args: argparse.Namespace) -> Path:
    return Path(args.data) if args.data is not None else CODE_DIR / DEFAULT_DATA_DIR


def cmd_validate(args: argparse.Namespace, report: Any) -> int:
    _stdout(summary(load_data(_data_dir(args), report)))
    return EXIT_OK


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------


def _real(path: Path) -> Path:
    return Path(os.path.realpath(Path(path).absolute()))


def _same(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return first == second


def is_inside(path: Path, directory: Path, *, strict: bool = False) -> bool:
    """True when `path` lies inside `directory` (or is it, unless `strict`),
    symbolic links resolved and letter case as the file system sees it."""
    resolved, target = _real(path), _real(directory)
    candidates = resolved.parents if strict else (resolved, *resolved.parents)
    return any(_same(candidate, target) for candidate in candidates)


def check_out(out_dir: Path, data_dir: Path) -> None:
    """Refuse an `--out` whose replacement would destroy anything.

    First not inside `--data`, then the rules of `check_out_dir`: not the
    code, the data or the working directory nor a parent of one, not inside
    `assets/` of the code, and an existing directory only when it looks like
    a previous build.  The messages never repeat a path: the data is not read
    yet, so no token is known to hide.
    """
    from menu_tools import _core

    if is_inside(out_dir, data_dir, strict=True):
        raise _core.BuildError(
            "--out must not lie inside the data directory (--data): the build never writes "
            "there; choose a separate output directory"
        )
    _core.check_out_dir(out_dir, code_dir=CODE_DIR, data_dir=data_dir, media_dir=data_dir)


def load_palette() -> Any:
    """The colours of the design tokens of `assets/app.css` (the colour of the
    browser interface and the icon); `assets/favicon.svg` of the code would
    take the place of the generated icon and is refused."""
    from menu_tools import _core

    assets = CODE_DIR / ASSETS_DIR
    try:
        taken = sorted(name for name in os.listdir(assets) if name.lower() == FAVICON_FILE)
    except OSError:
        taken = []  # reported when the assets are copied
    if taken:
        raise _core.BuildError(
            f"{ASSETS_DIR}/{taken[0]} of the code collides with the icon that the build "
            "generates from the design tokens; remove it"
        )
    try:
        return _core.load_palette(assets / TOKENS_FILE)
    except _core.TokenError as exc:
        raise _core.BuildError(
            f"{ASSETS_DIR}/{exc} (the colour of the browser interface and the icon are "
            "taken from the design tokens)"
        ) from None


def render_page(template: Any, tree: dict) -> str:
    """One page: the template rendered on its tree, without HTML comments
    (notes of the template are never published)."""
    from menu_tools import _core

    return _core.strip_html_comments(template.render(tree), template.name)


def render_pages(template: Any, pages: list) -> list[tuple[str, str]]:
    """(token, HTML) of every page, rendered in memory: a broken template
    leaves no half-written output behind.

    A problem of the template is reported once for all the pages it hits:
    `guests.json: guest #N: <problem>` for one record,
    `<k> guest record(s): <problem>; first: guests.json: guest #N` for more.
    """
    from menu_tools import _core, _schema

    rendered: list[tuple[str, str]] = []
    failures: dict[str, list[int]] = {}  # problem -> numbers of the records
    for page in pages:
        try:
            rendered.append((page.token, render_page(template, page.tree)))
        except _core.TemplateError as exc:
            failures.setdefault(str(exc), []).append(page.number)
    if failures:
        raise _core.ValidationError(
            f"{_schema.guest_where(numbers[0])}: {problem}"
            if len(numbers) == 1
            else f"{len(numbers)} guest record(s): {problem}; first: {_schema.guest_where(min(numbers))}"
            for problem, numbers in failures.items()
        )
    return rendered


def write_favicon(path: Path, palette: Any) -> None:
    from menu_tools import _core

    try:
        path.write_bytes(_core.favicon_svg(palette))
    except OSError as exc:
        raise _core.BuildError(f"cannot write {ASSETS_DIR}/{FAVICON_FILE}: {exc.strerror}") from None


def cmd_build(args: argparse.Namespace, report: Any) -> int:
    """Check `--out`, read the data, render the pages, write the output next
    to `--out`, check it and swap it in; the log shows counters and paths
    (directories named after tokens are hidden), never data."""
    from menu_tools import _core, _output, _page

    data_dir = _data_dir(args)
    out_dir = Path(args.out) if args.out is not None else DEFAULT_OUT_DIR
    base_path = args.base_path or DEFAULT_BASE_PATH

    def log(message: str) -> None:
        _stdout(report.redact(message))

    check_out(out_dir, data_dir)
    palette = load_palette()
    settings = _page.Settings(_core.assets_url_path(base_path), _core.hex_color(palette.surface))
    data = load_data(data_dir, report, settings)
    pages = pages_of(data)
    tokens = [page.token for page in pages]
    staff = " + staff" if data.trees.staff is not None else ""
    log(f"build: {data.index.guests} guest record(s){staff} validated (data: {_core.display_path(data_dir)})")

    template = _core.load_template(CODE_DIR / TEMPLATE_FILE)
    rendered = render_pages(template, pages)
    with _core._StagedOutput(out_dir, warn=report.warn) as temporary:
        written = _core.write_pages(temporary, rendered)
        copied = _core.copy_assets(CODE_DIR / ASSETS_DIR, temporary / ASSETS_DIR)
        write_favicon(temporary / ASSETS_DIR / FAVICON_FILE, palette)
        stats = _output.check_menu_output(
            temporary, tokens, base_path=base_path, numbers={page.token: page.number for page in pages}
        )

    out_shown = _core.display_path(out_dir)
    log(f"build: wrote {written} page(s) to {out_shown}/<token>/")
    log(
        f"build: base path {base_path}: the pages are at {base_path.rstrip('/')}/<token>/, "
        f"the shared files at {_core.assets_url_path(base_path)}/"
    )
    log(
        f"build: copied {copied} asset file(s) to {out_shown}/{ASSETS_DIR}/, "
        f"{FAVICON_FILE} generated from the design tokens"
    )
    log(
        f"build: OK -> {out_shown} ({written} page(s), {stats.files} file(s) in total, "
        f"{_core.format_size(stats.size)})"
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# links and token
# --------------------------------------------------------------------------


def page_links(url: str, data: Data) -> list[str]:
    """`<name><TAB><url>/<token>/` for every guest record in the order of
    `guests.json` (the white space of the name collapsed), then
    `staff<TAB><url>/<token>/` for the staff record, if any."""
    lines = [
        f"{' '.join(data.guests[page.number - 1]['name'].split())}\t{url}/{page.token}/"
        for page in data.trees.guests
    ]
    if data.trees.staff is not None:
        lines.append(f"staff\t{url}/{data.trees.staff.token}/")
    return lines


def cmd_links(args: argparse.Namespace, report: Any) -> int:
    from menu_tools import _core

    if _core.running_in_ci():
        raise _core.BuildError(
            "this command prints personal data and is meant for local use only; it does not "
            f"run in CI ({' or '.join(_core.CI_ENVIRONMENT_VARIABLES)} is set)"
        )
    data = load_data(_data_dir(args), report)
    # nothing is printed unless the whole data set is valid
    for line in page_links(args.url, data):
        _stdout(line)
    return EXIT_OK


def cmd_token(args: argparse.Namespace, report: Any) -> int:
    from menu_tools import _core

    prefix = args.prefix
    _stdout(_core.generate_token() if prefix is None else _core.generate_prefixed_token(prefix))
    return EXIT_OK


# --------------------------------------------------------------------------
# Running a command
# --------------------------------------------------------------------------

#: The function of every command.
COMMAND_FUNCTIONS = {
    "build": cmd_build,
    "validate": cmd_validate,
    "links": cmd_links,
    "token": cmd_token,
}


def debug_enabled() -> bool:
    """`BUILD_DEBUG=1` (or `true` / `yes`) shows tracebacks of internal errors."""
    return os.environ.get("BUILD_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def run_command(command: Any, args: argparse.Namespace) -> int:
    """Run a command; every message passes the report, which hides the tokens."""
    from menu_tools import _core

    report = cli_report()
    try:
        return int(command(args, report))
    except _core.ValidationError as exc:
        for message in exc.errors:
            _stderr(f"error: {report.redact(message)}")
        _stderr(f"{args.command}: failed with {len(exc.errors)} error(s)")
        return EXIT_ERROR
    except _core.BuildError as exc:
        _stderr(f"error: {report.redact(exc)}")
        _stderr(f"{args.command}: failed")
        return EXIT_ERROR
    except OSError as exc:
        # before the data is read no token is known to hide: the file is not
        # named then (it may lie in the directory of a page)
        where = f": {_core.display_path(exc.filename)}" if exc.filename and report.tokens else ""
        _stderr(f"error: {report.redact(f'{exc.strerror or type(exc).__name__}{where}')}")
        _stderr(f"{args.command}: failed")
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        _stderr(f"{args.command}: interrupted")
        return EXIT_ERROR
    except Exception as exc:  # unexpected: report without leaking data
        if debug_enabled():
            traceback.print_exc()
        else:
            # The message of the exception may quote the data, so only its
            # type and the place in the code are shown.
            frames = traceback.extract_tb(exc.__traceback__)
            where = f" at {os.path.basename(frames[-1].filename)}:{frames[-1].lineno}" if frames else ""
            _stderr(f"error: internal error: {type(exc).__name__}{where} (set BUILD_DEBUG=1 for the traceback)")
        _stderr(f"{args.command}: failed")
        return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    """Run the command line; argparse exits by itself on `--help` and usage
    errors (code 2)."""
    args = make_parser().parse_args(argv)
    return run_command(COMMAND_FUNCTIONS[args.command], args)


if __name__ == "__main__":
    sys.exit(main())
