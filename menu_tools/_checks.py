"""Messages of the checks of a JSON document.

`_Checker` reports the problems of the fields of one document to a report
object with the methods `error(text)` and `warning(text)` (`warn` is accepted
as well).  Messages have the form `<where>: field '<path>' <problem>` and
never quote the data.  With a set of known keys a key or an id is shown only
when it is one of them: such a key may be somebody's name, so every other key
is replaced by a neutral label.  `MISSING` is what the methods return for a
field without a usable value.

Standard library only; no input/output.
"""

from __future__ import annotations

from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

from menu_tools import _values as _data
from menu_tools._values import (
    ID_RULE,
    PathPart,
    did_you_mean,
    format_path,
    is_identifier,
    json_type,
    show_id,
)


#: A video is published as one file that every browser plays.
VIDEO_EXTENSIONS = frozenset({".mp4"})


#: How many known ids a message lists at most.
MAX_LISTED = 8


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MISSING"


#: "No usable value": the field is absent or its problem is reported.
MISSING: Any = _Missing()


def report_warning(report: Any) -> Callable[[str], None]:
    """The warning method of a report: `warning`, else `warn`."""
    method = getattr(report, "warning", None)
    return method if callable(method) else report.warn


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------


class _Checker:
    """Messages about one document or one invitation.

    `known` switches on the strict mode of `format_path`: only these keys
    are shown.  `errors` counts the errors reported through the checker.
    """

    def __init__(self, report: Any, where: str, known: Collection[str] | None = None):
        self.report = report
        self.where = where
        self.known = known
        self.errors = 0
        self._warning = report_warning(report)

    def path(self, parts: Sequence[PathPart]) -> str:
        return format_path(parts, self.known)

    def _text(self, parts: Sequence[PathPart], problem: str) -> str:
        subject = f"field '{self.path(parts)}' " if parts else ""
        return f"{self.where}: {subject}{problem}"

    def error(self, parts: Sequence[PathPart], problem: str) -> None:
        self.errors += 1
        self.report.error(self._text(parts, problem))

    def warning(self, parts: Sequence[PathPart], problem: str) -> None:
        self._warning(self._text(parts, problem))

    def raw_error(self, message: str) -> None:
        """A message that is not about one field (already worded)."""
        self.errors += 1
        self.report.error(f"{self.where}: {message}")

    def show(self, value: Any) -> str:
        """An id for a message; in strict mode only a known one."""
        if self.known is not None and value not in self.known:
            return ""
        return show_id(value)

    # -- shapes ------------------------------------------------------------

    def unknown_fields(
        self,
        obj: dict,
        allowed: Sequence[str],
        parts: Sequence[PathPart],
        hints: Mapping[str, str] | None = None,
    ) -> None:
        # default: a misspelt field name is an error, not a warning
        # default: keys that start with "_" are not skipped (no comments in JSON)
        for key in obj:
            if key in allowed:
                continue
            where = (*parts, key)
            hint = (hints or {}).get(key)
            if hint:
                self.error(where, hint)
            else:
                self.errors += 1
                self.report.error(
                    f"{self.where}: unknown field '{self.path(where)}'"
                    f"{did_you_mean(key, allowed)}"
                )

    def object(self, value: Any, parts: Sequence[PathPart]) -> dict | None:
        if isinstance(value, dict):
            return value
        self.error(parts, f"must be an object, got {json_type(value)}")
        return None

    def value(
        self,
        obj: dict,
        key: str,
        kind: str,
        parts: Sequence[PathPart],
        *,
        required: bool = False,
        single_line: bool = False,
    ) -> Any:
        """A field of `kind`: string, boolean, number, count, array, object.

        An empty string counts as "not set".  `null` is never accepted.
        """
        where = (*parts, key)
        if key not in obj:
            if required:
                self.error(where, "is required")
            return MISSING
        value = obj[key]
        expected = _KINDS[kind]
        if not expected[1](value):
            self.error(where, f"must be {expected[0]}, got {json_type(value)}")
            return MISSING
        if kind == "string":
            if not value.strip():
                if required:
                    self.error(where, "must not be empty")
                return MISSING
            if single_line and ("\n" in value or "\r" in value):
                self.error(where, "must be a single line (no line breaks)")
                return MISSING
        if kind == "number" and not _data._is_finite(value):
            self.error(where, "must be a finite number")
            return MISSING
        return value

    def choice(
        self, obj: dict, key: str, allowed: Sequence[str], parts: Sequence[PathPart]
    ) -> Any:
        """A field that holds one of `allowed` (the value is never shown)."""
        if key not in obj:
            return MISSING
        if obj[key] not in allowed or not isinstance(obj[key], str):
            self.error((*parts, key), f"must be one of: {', '.join(allowed)}")
            return MISSING
        return obj[key]

    def ref(
        self,
        value: Any,
        parts: Sequence[PathPart],
        registry: Mapping[str, Any] | None,
        what: str,
    ) -> str | None:
        """A reference by id; None when it cannot be used."""
        if not isinstance(value, str):
            self.error(parts, f"must be the id of {_article(what)}, got {json_type(value)}")
            return None
        if registry is None:
            return None  # the registry itself is broken and reported
        if value in registry:
            return value
        if self.known is None and not is_identifier(value):
            self.error(parts, f"must be the id of {_article(what)}: {ID_RULE}")
            return None
        shown = self.show(value)
        self.error(
            parts,
            f"refers to an unknown {what}{' ' + shown if shown else ''}"
            f"{did_you_mean(value, registry)}{_known_list(registry, what)}",
        )
        return None

    def ref_list(
        self,
        obj: dict,
        key: str,
        parts: Sequence[PathPart],
        registry: Mapping[str, Any] | None,
        what: str,
        *,
        required: bool,
        allow_empty: bool,
    ) -> list[str] | None:
        values = self.value(obj, key, "array", parts, required=required)
        if values is MISSING:
            return None
        where = (*parts, key)
        if not values and not allow_empty:
            self.error(where, f"must list at least one {what}")
            return None
        seen: list[str] = []
        for position, value in enumerate(values):
            found = self.ref(value, (*where, position), registry, what)
            if found is None:
                continue
            if found in seen:
                self.error((*where, position), f"repeats {show_id(found)}")
                continue
            seen.append(found)
        return seen


_KINDS: dict[str, tuple[str, Callable[[Any], bool]]] = {
    "string": ("a string", lambda v: isinstance(v, str)),
    "boolean": ("a boolean (true or false)", lambda v: isinstance(v, bool)),
    "number": ("a number", lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)),
    "count": (
        "a positive whole number",
        lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0,
    ),
    "array": ("an array", lambda v: isinstance(v, list)),
    "object": ("an object", lambda v: isinstance(v, dict)),
}


def _article(what: str) -> str:
    return f"an {what}" if what[0] in "aeiou" else f"a {what}"


def _known_list(registry: Iterable[str], what: str) -> str:
    known = [item for item in registry if is_identifier(item)]
    if not known:
        return f"; there are no {what}s"
    listed = ", ".join(known[:MAX_LISTED])
    return f"; known: {listed}{', …' if len(known) > MAX_LISTED else ''}"
