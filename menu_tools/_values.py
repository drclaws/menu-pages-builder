"""Helpers of the data layer: JSON, field paths, hints, ids and tokens.

- `parse_json` reads a document like `json.loads` and also lists every key
  that is repeated within one object, at any depth: plain `json.loads`
  silently keeps the last value only, and the rest of the data is lost.
- `format_path` writes a field path: `sections[3].widgets[1].location`.
- `did_you_mean` suggests the closest of the known names.
- `is_identifier`, `show_id`: the rule for ids.
- Tokens and sizes: `check_token`, `generate_token`,
  `generate_prefixed_token`, `json_type` and `format_size`.

Messages never quote the data.  A key is shown only when it looks like a
field name or an id (`is_plain_key`); in strict mode (`known`), where a key
may be somebody's name, only when it is one of the known names.  An id is
shown only when it follows the id rule.  Messages have the form
`field '<path>' <problem>`; the caller puts the file or record name in
front.

Pure functions: no input/output and no printing (the two token generators
alone read the random source).  Problems are returned as messages.  Standard
library only.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import secrets
from typing import Any, Callable, Collection, Iterable, Mapping, NamedTuple, Union

#: One step of a field path: the key of an object or an index in an array.
PathPart = Union[str, int]

# --------------------------------------------------------------------------
# Keys and field paths
# --------------------------------------------------------------------------

#: A key that looks like a field name or an id is shown as it is.
_PLAIN_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
MAX_PLAIN_KEY_LENGTH = 64
#: Shown instead of any other key: such a key may hold somebody's name.
HIDDEN_KEY = "<non-identifier key>"


def is_plain_key(key: Any) -> bool:
    """True for a key that may appear in a message as it is."""
    return (
        isinstance(key, str)
        and len(key) <= MAX_PLAIN_KEY_LENGTH
        and _PLAIN_KEY_RE.fullmatch(key) is not None
    )


#: Shown in strict mode instead of a key that is not one of the known names.
UNKNOWN_KEY = "<unknown key>"


def _key_text(key: Any, known: Collection[str] | None) -> str:
    """The key itself, or the neutral label that stands for it."""
    if known is None:
        return key if is_plain_key(key) else HIDDEN_KEY
    # strict mode: in data where a key may be somebody's name, only the names
    # that the caller knows to be safe are ever shown
    return key if is_plain_key(key) and key in known else UNKNOWN_KEY


def show_key(key: Any, known: Collection[str] | None = None) -> str:
    """A key for a message: `'hotel'`, or a neutral label for any other key.

    With `known` (strict mode) a key is shown only when it is one of `known`,
    whatever it looks like: `UNKNOWN_KEY` stands for every other key.
    """
    text = _key_text(key, known)
    return f"'{text}'" if text == key else text


def format_path(parts: Iterable[PathPart], known: Collection[str] | None = None) -> str:
    """`("sections", 3, "id")` -> `sections[3].id`; no parts -> `top level`.

    `known` switches `show_key` to strict mode for the keys.
    """
    text = ""
    for part in parts:
        if isinstance(part, int) and not isinstance(part, bool):
            text += f"[{part}]"
        else:
            name = _key_text(part, known)
            text += f".{name}" if text else name
    return text or "top level"


# --------------------------------------------------------------------------
# "Did you mean"
# --------------------------------------------------------------------------

#: Minimal similarity (`difflib`) for a known name to be suggested.
SUGGESTION_CUTOFF = 0.6


def closest_name(name: Any, known: Iterable[str]) -> str | None:
    """The known name most similar to `name`, if any is similar enough."""
    if not isinstance(name, str):
        return None
    candidates = [item for item in known if isinstance(item, str)]
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=SUGGESTION_CUTOFF)
    return matches[0] if matches else None


def did_you_mean(name: Any, known: Iterable[str]) -> str:
    """` (did you mean 'visible'?)` or an empty string.

    Only a known name is ever shown (and only one that passes `is_plain_key`),
    never `name` itself.
    """
    match = closest_name(name, known)
    if match is None or not is_plain_key(match):
        return ""
    return f" (did you mean {show_key(match)}?)"


# --------------------------------------------------------------------------
# JSON with repeated keys
# --------------------------------------------------------------------------


class DuplicateKey(NamedTuple):
    """A key that appears more than once in one JSON object."""

    #: Path to the object, from the top of the document.
    path: tuple[PathPart, ...]
    key: str

    def describe(self, known: Collection[str] | None = None) -> str:
        """The message; `known` switches `show_key` to strict mode."""
        where = f"in '{format_path(self.path, known)}'" if self.path else "at the top level"
        return (
            f"duplicate key {show_key(self.key, known)} {where} "
            "(JSON keeps only the last one; merge or rename them)"
        )


def parse_json(
    text: str, *, parse_constant: Callable[[str], Any] | None = None
) -> tuple[Any, list[DuplicateKey]]:
    """Parse a JSON document and list the keys repeated within an object.

    The value is exactly what `json.loads` returns (of repeated keys the last
    value wins).  Every repeated key is listed once per object, depth first;
    objects inside a value that a repeated key replaced are searched as well.
    Syntax errors are raised by `json.loads` (`json.JSONDecodeError`, or what
    `parse_constant` raises).
    """
    # id(object) -> (object, repeated keys, replaced (key, value) pairs); the
    # object is kept here so that its id cannot be reused while this runs
    repeated: dict[int, tuple[dict, list[str], list[tuple[str, Any]]]] = {}

    def make_object(pairs: list[tuple[str, Any]]) -> dict:
        obj: dict = {}
        keys: list[str] = []
        replaced: list[tuple[str, Any]] = []
        for key, value in pairs:
            if key in obj:
                if key not in keys:
                    keys.append(key)
                replaced.append((key, obj[key]))
            obj[key] = value
        if keys:
            repeated[id(obj)] = (obj, keys, replaced)
        return obj

    value = json.loads(text, object_pairs_hook=make_object, parse_constant=parse_constant)
    return value, (_find_duplicates(value, repeated) if repeated else [])


def _find_duplicates(
    root: Any, repeated: Mapping[int, tuple[dict, list[str], list[tuple[str, Any]]]]
) -> list[DuplicateKey]:
    # an explicit stack: the parser has already accepted the nesting depth,
    # a recursive walk might not
    found: list[DuplicateKey] = []
    stack: list[tuple[tuple[PathPart, ...], Any]] = [((), root)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict):
            members = list(value.items())
            record = repeated.get(id(value))
            if record is not None and record[0] is value:
                found.extend(DuplicateKey(path, key) for key in record[1])
                members = record[2] + members
            stack.extend(((*path, key), item) for key, item in reversed(members))
        elif isinstance(value, list):
            indexed = list(enumerate(value))
            stack.extend(((*path, index), item) for index, item in reversed(indexed))
    return found


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------

#: Lowercase Latin letters and digits in words joined by single hyphens,
#: starting with a letter (`--` stays free as a separator of composite ids).
_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
MAX_ID_LENGTH = 32
ID_RULE = (
    f"1-{MAX_ID_LENGTH} characters, lowercase a-z, 0-9 and single hyphens, "
    "starting with a letter"
)


def is_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_ID_LENGTH
        and _ID_RE.fullmatch(value) is not None
    )


def show_id(value: Any) -> str:
    """An id for a message: `'hotel'`; any other value is not shown."""
    return f"'{value}'" if is_identifier(value) else "(not a valid identifier)"


# --------------------------------------------------------------------------
# JSON types and sizes
# --------------------------------------------------------------------------


def _is_finite(value: int | float) -> bool:
    """False for infinities, NaN and integers too large to fit into a float."""
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def json_type(value: Any) -> str:
    """Name of a value's JSON type, for error messages (never the value)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def format_size(size: int) -> str:
    """A byte count for the log: `512 B`, `1.5 KiB`, `25.0 MiB`."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.1f} MiB"


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

#: Tokens are written by the owners and may be short and readable: the token
#: is the only thing that protects a page from being guessed.
MIN_TOKEN_LENGTH = 5
#: `token --prefix NAME` appends `-` and this many random characters.
TOKEN_SUFFIX_LENGTH = 4
#: Lower case letters and digits without the ones that are easy to confuse
#: (0/o, 1/l/i): the tail is read and typed by people.
TOKEN_SUFFIX_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
#: Tokens become directory names, so their length is capped well
#: below the file name limit of common file systems (255 bytes).
MAX_NAME_LENGTH = 200

_TOKEN_CHARS_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
#: Names a token must not take, in lower case: the pages are directories next
#: to `assets/`, the directory of the files they share.
RESERVED_TOKENS = frozenset({"assets"})


def check_token(token: Any) -> str | None:
    """Return a problem description for `token`, or None when it is valid.

    The description never repeats the token, nor a reserved name it matches.
    """
    if not isinstance(token, str):
        return f"'token' must be a string, got {json_type(token)}"
    if not token:
        return "'token' is empty"
    if not _TOKEN_CHARS_RE.match(token):
        return "'token' may only contain A-Z, a-z, 0-9, '_' and '-'"
    if len(token) > MAX_NAME_LENGTH:
        return (
            f"'token' is too long: at most {MAX_NAME_LENGTH} characters allowed "
            f"(it becomes a directory name), got {len(token)}"
        )
    if len(token) < MIN_TOKEN_LENGTH:
        return (
            f"'token' is too short: at least {MIN_TOKEN_LENGTH} characters required, "
            f"got {len(token)}"
        )
    if token.lower() in RESERVED_TOKENS:
        return (
            "'token' is a reserved name: its page directory would be the shared-files "
            "directory (letter case aside); choose another token"
        )
    return None


def generate_token() -> str:
    """A fresh URL-safe token that passes `check_token`."""
    while True:
        token = secrets.token_urlsafe(16)
        if check_token(token) is None:
            return token


#: The longest prefix that leaves room for `-` and the random tail.
MAX_TOKEN_PREFIX_LENGTH = MAX_NAME_LENGTH - 1 - TOKEN_SUFFIX_LENGTH


def check_token_prefix(prefix: Any) -> str | None:
    """Return a problem description for the NAME of `token --prefix`, or None."""
    if not isinstance(prefix, str) or not prefix:
        return "the prefix is empty"
    if not _TOKEN_CHARS_RE.match(prefix):
        return "the prefix may only contain A-Z, a-z, 0-9, '_' and '-'"
    if len(prefix) > MAX_TOKEN_PREFIX_LENGTH:
        return (
            f"the prefix is too long: at most {MAX_TOKEN_PREFIX_LENGTH} characters "
            f"allowed, got {len(prefix)}"
        )
    return None


def generate_prefixed_token(prefix: str) -> str:
    """`<prefix>-xxxx`: a readable token with a short random tail.

    The tail comes from `secrets`, so the token cannot be guessed from a list
    of names alone.  `ValueError` when the prefix breaks `check_token_prefix`.
    """
    problem = check_token_prefix(prefix)
    if problem:
        raise ValueError(problem)
    tail = "".join(secrets.choice(TOKEN_SUFFIX_ALPHABET) for _ in range(TOKEN_SUFFIX_LENGTH))
    return f"{prefix}-{tail}"
