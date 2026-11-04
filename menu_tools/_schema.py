"""Checks of the menu data: `menu.json` and `guests.json`.

`check_menu` checks the shared data of the menu and returns a `MenuIndex`,
what the other checks and the page trees need to know about it;
`check_guests` checks the personal records against it; `check_data` runs
both.  Every problem goes to a report object with `error(text)` and
`warning(text)` (or `warn(text)`); nothing is raised.  `check_usage` turns
what the finished page trees show into warnings (a dish no page shows).

Messages have the form `<file>: field '<path>' <problem>` and
`guests.json: guest #N: field '<path>' <problem>` (N is the position of the
record in the file, from 1; the staff record is counted too) and never quote
the data.  In `guests.json` a key is shown only when it is a field name of
the format or an id declared in `menu.json`; every other key may be a name
and is shown as `<unknown key>`.  A seat number is shown only when the menu
has a table that has the seat.

The table and the couple are checked by `menu_tools._table`; its messages
name their place in their own way (`table.arms[2]: ...`) and are reported
as they are, after the name of the file.

Standard library only; no input/output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from menu_tools import _table
from menu_tools._core import (
    ID_RULE,
    SCHEMA_MISSING as MISSING,
    _Checker,
    _known_list,
    check_token,
    did_you_mean,
    is_identifier,
    json_type,
    show_id,
)

SCHEMA_VERSION = 1
MENU_FILE = "menu.json"
GUESTS_FILE = "guests.json"

#: Who sees a section or a widget (the first one is the default).
AUDIENCES = ("all", "guest", "staff")

MENU_FIELDS = (
    "schemaVersion",
    "coupleNames",
    "event",
    "staff",
    "requirements",
    "allergens",
    "couple",
    "reservedSeats",
    "table",
    "dishes",
    "sets",
    "drinks",
    "sections",
)
EVENT_FIELDS = ("title", "when", "place")
ROOT_STAFF_FIELDS = ("updated", "contact", "reminder")
REQUIREMENT_FIELDS = ("letter", "label", "tag", "avoids")
ALLERGEN_FIELDS = ("label",)
COUPLE_FIELDS = ("label", "arm", "members")
MEMBER_FIELDS = ("seat", "name", "role", "requirements")
DISH_FIELDS = ("name", "ingredients", "staff")
DISH_STAFF_FIELDS = ("allergens", "tags", "swaps", "note")
SET_FIELDS = ("title", "hint", "eyebrow", "courses", "pairing")
DRINKS_FIELDS = ("categories", "items")
CATEGORY_FIELDS = ("label",)
DRINK_FIELDS = ("category", "name", "details", "servedWith", "staff")
DRINK_STAFF_FIELDS = ("bottles", "serving", "swaps")

SECTION_TYPES = ("cover", "custom")
#: `nav` is the short label of a section in the line of the sections at the
#: top of a page; a section without one has no link there.
SECTION_FIELDS = {
    "cover": ("id", "type"),
    "custom": ("id", "type", "visible", "audience", "title", "eyebrow", "nav", "staff", "widgets"),
}
SECTION_STAFF_FIELDS = ("title", "eyebrow")
#: `heading` is the head of a part of a section: what follows it, up to the
#: next heading, is the part (`dishes.title` is a caption of its list, not a
#: heading).
WIDGET_TYPES = ("text", "seating", "dishes", "sets", "drinks", "heading")
WIDGET_BASE_FIELDS = ("type", "id", "visible", "audience")
WIDGET_FIELDS = {
    "text": ("text", "variant"),
    "seating": ("showScheme", "showLegend", "showTable", "staff"),
    "dishes": ("items", "title"),
    "sets": ("items", "note", "staff"),
    "drinks": ("groups", "note", "staff"),
    "heading": ("title", "eyebrow", "staff"),
}
#: The fields under the `staff` key of a widget: what only the staff page
#: shows (the texts of a heading replace those of the guests there).
WIDGET_STAFF_FIELDS = {
    "seating": ("footnote",),
    "sets": ("note",),
    "drinks": ("note",),
    "heading": ("title", "eyebrow"),
}
#: Nothing of a section stands under such a heading on any page.
_EMPTY_HEADING = "nothing stands under the heading"
#: What a section without `nav` is.
_NO_LABEL = "leave the field out for a section without a link in the line of the sections"
TEXT_VARIANTS = ("body", "lead", "card", "signature")
GROUP_FIELDS = ("title", "layout", "items")
GROUP_LAYOUTS = ("list", "inline")

GUEST_FIELDS = ("token", "name", "seats", "sections")
STAFF_RECORD_FIELDS = ("token", "staff")
SEAT_FIELDS = ("number", "plusOne", "name", "requirements")
GUEST_SECTION_FIELDS = ("visible", "note", "widgets")
GUEST_WIDGET_FIELDS = ("visible",)
#: Every field name of a record: always safe to show.
GUEST_FIELD_NAMES = frozenset(
    {*GUEST_FIELDS, *STAFF_RECORD_FIELDS, *SEAT_FIELDS, *GUEST_SECTION_FIELDS}
)

#: The largest seat number of a menu without a table.
MAX_SEAT = 999
#: The staff page shows every name and every dietary note: a shorter token
#: of the staff record gets a warning.
STAFF_TOKEN_MIN = 16

#: The placeholder of a token: no text of the menu may hold it, the pages of
#: the menu hold no token.
TOKEN_PLACEHOLDER = "{token}"
_LETTER_RE = re.compile(r"[A-Z]")

_STAFF_ONLY_HINT = "is not allowed in the staff record: it has a token and nothing else"
#: A guest cannot switch on a part for the staff only, so a hidden one is
#: never shown.
_HIDDEN_STAFF_PART = "hides a part for the staff only: no page ever shows it (a guest cannot switch it on)"


def guest_label(number: int) -> str:
    """The name of a record in messages: its position in `guests.json`."""
    return f"guest #{number}"


def guest_where(number: int) -> str:
    """The beginning of a message about a record."""
    return f"{GUESTS_FILE}: {guest_label(number)}"


# --------------------------------------------------------------------------
# What the checks learn
# --------------------------------------------------------------------------


@dataclass
class MenuIndex:
    """What `check_menu` and `check_guests` learned; a registry is None when
    it is broken (its problem is reported)."""

    #: `menu.json` is an object with the supported `schemaVersion`.
    version_ok: bool = False
    #: Number of errors in `menu.json` (the couple and the table included).
    errors: int = 0
    #: Number of errors in `guests.json`.
    guest_errors: int = 0

    requirements: dict | None = None
    allergens: dict | None = None
    dishes: dict | None = None
    sets: dict | None = None
    categories: dict | None = None
    drinks: dict | None = None

    #: The menu has a `table` (whatever its problems).
    has_table: bool = False
    #: The table passes its check: seats can be laid out.
    table_ok: bool = False
    #: The number of seats of the table, when it can be counted.
    total: int | None = None
    #: Seat -> position of the member of the couple who sits there.
    couple_seats: dict[int, int] = field(default_factory=dict)
    #: Seat -> its position in `reservedSeats` (only with a table: without
    #: one the list has no effect).
    reserved: dict[int, int] = field(default_factory=dict)
    #: Seat -> who sits there ("the couple", "guest #2").
    taken: dict[int, str] = field(default_factory=dict)
    #: Seat -> the ids of its requirements (the couple included).
    seat_requirements: dict[int, list[str]] = field(default_factory=dict)

    #: Sections with a usable id, by id.
    sections: dict[str, dict] = field(default_factory=dict)
    #: Section id -> the ids of its widgets.
    widget_ids: dict[str, list[str]] = field(default_factory=dict)
    #: (section id, widget id) -> who sees the widget: guest, staff or all.
    widget_audience: dict[tuple[str, str], str] = field(default_factory=dict)
    #: False when a section has no usable id or type: the references of the
    #: records to sections are not checked then.
    sections_ok: bool = True
    #: Sections whose widgets are broken: references to them are not checked.
    broken_widgets: set[str] = field(default_factory=set)
    #: The parts of the menu for the staff only, as paths.
    staff_parts: list[str] = field(default_factory=list)

    #: Number of guest records and the number of the staff record (0: none).
    guests: int = 0
    staff_record: int = 0
    #: A record has the field `staff`, even a broken one: it is meant to be
    #: the staff record, so "no staff record" would repeat its error.
    staff_claimed: bool = False

    def declared_ids(self) -> frozenset[str]:
        """Ids a record may refer to: safe to show in its messages."""
        ids = set(self.sections) | set(self.requirements or ())
        for widgets in self.widget_ids.values():
            ids.update(widgets)
        return frozenset(item for item in ids if is_identifier(item))

    @property
    def ok(self) -> bool:
        """No error in either file: the pages can be built."""
        return self.version_ok and not self.errors and not self.guest_errors

    @property
    def seats(self) -> int:
        """The seats of the menu: those of the table, else the taken ones."""
        return self.total if self.table_ok and self.total is not None else len(self.taken)


def guest_known(index: MenuIndex) -> frozenset[str]:
    """The keys a message about `guests.json` may show (`read_json`)."""
    return GUEST_FIELD_NAMES | index.declared_ids()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _braces(check: _Checker, value: Any, where: Sequence) -> bool:
    """False (and an error) for a text with template syntax or the
    placeholder of a token."""
    if not isinstance(value, str):
        return True
    if "{{" in value or "}}" in value:
        check.error(where, "must not contain '{{' or '}}' (the texts of the menu have no template syntax)")
        return False
    if TOKEN_PLACEHOLDER in value:
        check.error(where, "must not contain '{token}': the pages of the menu hold no token")
        return False
    return True


def _line(check: _Checker, obj: dict, key: str, parts: Sequence, *, required: bool = False) -> Any:
    """A single-line text; MISSING when it is absent, empty or broken."""
    value = check.value(obj, key, "string", parts, required=required, single_line=True)
    if value is not MISSING and not _braces(check, value, (*parts, key)):
        return MISSING
    return value


def _text(check: _Checker, obj: dict, key: str, parts: Sequence, *, required: bool = False) -> Any:
    """A text that may have several lines."""
    value = check.value(obj, key, "string", parts, required=required)
    if value is not MISSING and not _braces(check, value, (*parts, key)):
        return MISSING
    return value


def _object(
    check: _Checker, obj: dict, key: str, parts: Sequence, fields: Sequence[str], *, required: bool = False
) -> dict | None:
    """An object field with known fields; None when it is absent or broken."""
    value = check.value(obj, key, "object", parts, required=required)
    if value is MISSING:
        return None
    check.unknown_fields(value, fields, (*parts, key))
    return value


def _registry(check: _Checker, obj: dict, key: str, parts: Sequence = (), *, required: bool = False) -> dict | None:
    """A registry `{id: entry}` without the entries whose key is not an id."""
    where = (*parts, key)
    if key not in obj:
        if required:
            check.error(where, "is required")
            return None
        return {}
    value = obj[key]
    if not isinstance(value, dict):
        check.error(where, f"must be an object {{ id: … }}, got {json_type(value)}")
        return None
    entries = {}
    for entry_id, entry in value.items():
        if is_identifier(entry_id):
            entries[entry_id] = entry
        else:
            check.error((*where, entry_id), f"is not an identifier: an id has {ID_RULE}")
    return entries


def _count(check: _Checker, value: Any, where: Sequence) -> int | None:
    """A positive whole number in a list; None (and an error) otherwise."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    check.error(where, f"must be a positive whole number, got {json_type(value)}")
    return None


def _in_range(check: _Checker, number: int, where: Sequence, index: MenuIndex) -> bool:
    """A seat number the menu can have: one of the table, or up to MAX_SEAT."""
    if index.total is not None:
        if number > index.total:
            check.error(where, f"is not a seat of the table: it has {index.total} seats")
            return False
    elif not index.has_table and number > MAX_SEAT:
        check.error(where, f"must be at most {MAX_SEAT}")
        return False
    return True


def _seat_text(number: int, index: MenuIndex) -> str:
    """`the seat 5` with a table, `a seat` without one (numbers are not shown)."""
    return f"the seat {number}" if index.has_table else "a seat"


def _blank(value: Any) -> bool:
    """True for an absent text: no value or an empty string."""
    return value is None or (isinstance(value, str) and not value.strip())


def _audience(value: Any) -> str:
    return value if value in AUDIENCES else "all"


def _badges(
    check: _Checker, menu: dict, index: MenuIndex, number: int, requirements: Sequence[str], where: Sequence
) -> None:
    """The dietary badges of a seat must fit around it on the staff plan."""
    if not index.table_ok or not requirements:
        return
    room = _table.badge_capacity(menu["table"], number)
    if len(requirements) > room:
        check.error(where, f"needs {len(requirements)} badges, seat {number} has room for {room}")


# --------------------------------------------------------------------------
# menu.json
# --------------------------------------------------------------------------


def check_menu(menu: Any, report: Any, where: str = MENU_FILE) -> MenuIndex:
    """Check `menu.json`; the result tells the other checks what exists."""
    check = _Checker(report, where)
    index = MenuIndex()
    if not isinstance(menu, dict):
        check.raw_error(f"the top-level value must be an object, got {json_type(menu)}")
        index.errors = check.errors
        return index
    if not _check_version(check, menu):
        index.errors = check.errors
        return index
    index.version_ok = True

    check.unknown_fields(menu, MENU_FIELDS, ())
    _line(check, menu, "coupleNames", (), required=True)
    event = _object(check, menu, "event", (), EVENT_FIELDS, required=True)
    if event is not None:
        for key in EVENT_FIELDS:
            _line(check, event, key, ("event",), required=True)
    staff = _object(check, menu, "staff", (), ROOT_STAFF_FIELDS)
    if staff is not None:
        _line(check, staff, "updated", ("staff",))
        _line(check, staff, "contact", ("staff",))
        _text(check, staff, "reminder", ("staff",))

    index.allergens = _check_allergens(check, menu)
    index.requirements = _check_requirements(check, menu, index)
    _check_table(check, menu, index)
    _check_reserved(check, menu, index)
    _check_couple(check, menu, index)
    index.dishes = _check_dishes(check, menu, index)
    index.sets = _check_sets(check, menu, index)
    _check_drinks(check, menu, index)
    _check_sections(check, menu, index)
    index.errors = check.errors
    return index


def _check_version(check: _Checker, menu: dict) -> bool:
    if "schemaVersion" not in menu:
        check.error(("schemaVersion",), f"is required (use {SCHEMA_VERSION})")
        return False
    version = menu["schemaVersion"]
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        shown = f" {version}" if isinstance(version, int) and not isinstance(version, bool) else f" {json_type(version)}"
        check.error(
            ("schemaVersion",),
            f"is{shown} - not supported: this version of the menu reads version {SCHEMA_VERSION} only",
        )
        return False
    return True


def _check_allergens(check: _Checker, menu: dict) -> dict | None:
    allergens = _registry(check, menu, "allergens")
    for allergen_id, item in (allergens or {}).items():
        parts = ("allergens", allergen_id)
        item = check.object(item, parts)
        if item is not None:
            check.unknown_fields(item, ALLERGEN_FIELDS, parts)
            _line(check, item, "label", parts, required=True)
    return allergens


def _check_requirements(check: _Checker, menu: dict, index: MenuIndex) -> dict | None:
    requirements = _registry(check, menu, "requirements")
    letters: dict[str, str] = {}
    for requirement_id, item in (requirements or {}).items():
        parts = ("requirements", requirement_id)
        item = check.object(item, parts)
        if item is None:
            continue
        check.unknown_fields(item, REQUIREMENT_FIELDS, parts)
        letter = check.value(item, "letter", "string", parts, required=True)
        if letter is not MISSING:
            if not _LETTER_RE.fullmatch(letter):
                check.error((*parts, "letter"), "must be one capital latin letter, A-Z")
            elif letter in letters:
                check.error((*parts, "letter"), f"repeats the letter of {show_id(letters[letter])}")
            else:
                letters[letter] = requirement_id
        _line(check, item, "label", parts, required=True)
        _line(check, item, "tag", parts)
        check.ref_list(item, "avoids", parts, index.allergens, "allergen", required=False, allow_empty=True)
    return requirements


def _check_table(check: _Checker, menu: dict, index: MenuIndex) -> None:
    if "table" not in menu:
        return
    index.has_table = True
    result = _table.check_table(menu["table"])
    for message in result.errors:
        check.raw_error(message)
    for message in result.warnings:
        check.warning((), message)
    index.total = result.total
    if not result.errors:
        index.table_ok = True
        index.total = len(_table.expand_seats(menu["table"]))


def _check_reserved(check: _Checker, menu: dict, index: MenuIndex) -> None:
    values = check.value(menu, "reservedSeats", "array", ())
    if values is MISSING:
        return
    if not index.has_table:
        check.warning(("reservedSeats",), "has no effect without 'table': only a table plan shows free seats")
    reserved: dict[int, int] = {}
    for position, value in enumerate(values):
        where = ("reservedSeats", position)
        number = _count(check, value, where)
        if number is None or not _in_range(check, number, where, index):
            continue
        if number in reserved:
            check.error(where, f"repeats {_seat_text(number, index)} of reservedSeats[{reserved[number]}]")
        else:
            reserved[number] = position
    # without a table the list has no effect: a record may take such a seat
    if index.has_table:
        index.reserved = reserved


def _check_couple(check: _Checker, menu: dict, index: MenuIndex) -> None:
    couple = _object(check, menu, "couple", (), COUPLE_FIELDS)
    if couple is None:
        return
    parts = ("couple",)
    label = _line(check, couple, "label", parts)
    arm = check.value(couple, "arm", "string", parts)
    if not index.has_table:
        for key, value in (("label", label), ("arm", arm)):
            if value is not MISSING:
                check.warning((*parts, key), "has no effect without 'table'")
    members = check.value(couple, "members", "array", parts, required=True)
    if members is MISSING:
        return
    seats: list[tuple[int, int]] = []  # (position, seat)
    seats_ok = True
    requirements: dict[int, list[str]] = {}
    for position, member in enumerate(members):
        member_parts = (*parts, "members", position)
        member = check.object(member, member_parts)
        if member is None:
            seats_ok = False
            continue
        check.unknown_fields(member, MEMBER_FIELDS, member_parts)
        seat = check.value(member, "seat", "count", member_parts, required=True)
        if seat is MISSING:
            seats_ok = False
        else:
            seats.append((position, seat))
        _line(check, member, "name", member_parts, required=True)
        _line(check, member, "role", member_parts)
        found = check.ref_list(
            member, "requirements", member_parts, index.requirements, "requirement",
            required=False, allow_empty=True,
        )
        if found:
            requirements[position] = found
    if not seats_ok:
        return
    numbers = [seat for _position, seat in seats]

    if index.has_table:
        # the number of members, their seats and the label against the table
        result = _table.check_couple(
            menu["table"],
            numbers,
            None if label is MISSING else label,
            arm if isinstance(arm, str) else None,
        )
        for message in result.errors:
            check.raw_error(message)
        for message in result.warnings:
            check.warning((), message)
        valid = (
            1 <= len(numbers) <= 2
            and len(set(numbers)) == len(numbers)
            and (index.total is None or all(number <= index.total for number in numbers))
        )
        if not valid:
            return
    else:
        if not 1 <= len(numbers) <= 2:
            check.error((*parts, "members"), "must list one or two members")
            return
        valid = True
        for position, seat in seats:
            if not _in_range(check, seat, (*parts, "members", position, "seat"), index):
                valid = False
        if len(numbers) == 2 and numbers[0] == numbers[1]:
            check.error((*parts, "members", seats[1][0], "seat"), "repeats the seat of couple.members[0]")
            valid = False
        if not valid:
            return

    for position, seat in seats:
        where = (*parts, "members", position, "seat")
        if seat in index.reserved:
            check.error(where, f"refers to {_seat_text(seat, index)}, which is reserved ('reservedSeats')")
            continue
        index.couple_seats[seat] = position
        index.taken[seat] = "the couple"
        found = requirements.get(position, [])
        index.seat_requirements[seat] = list(found)
        _badges(check, menu, index, seat, found, (*parts, "members", position, "requirements"))


def _check_swaps(check: _Checker, staff: dict, parts: Sequence, index: MenuIndex) -> None:
    swaps = check.value(staff, "swaps", "object", parts)
    if swaps is MISSING:
        return
    for requirement_id, text in swaps.items():
        where = (*parts, "swaps", requirement_id)
        if check.ref(requirement_id, where, index.requirements, "requirement") is None:
            continue
        if not isinstance(text, str) or not text.strip():
            check.error(where, "must be a non-empty string: what the waiter does for this requirement")
        elif "\n" in text or "\r" in text:
            check.error(where, "must be a single line (no line breaks)")
        else:
            _braces(check, text, where)


def _check_dishes(check: _Checker, menu: dict, index: MenuIndex) -> dict | None:
    dishes = _registry(check, menu, "dishes")
    for dish_id, dish in (dishes or {}).items():
        parts = ("dishes", dish_id)
        dish = check.object(dish, parts)
        if dish is None:
            continue
        check.unknown_fields(dish, DISH_FIELDS, parts)
        _line(check, dish, "name", parts, required=True)
        _line(check, dish, "ingredients", parts)
        staff = _object(check, dish, "staff", parts, DISH_STAFF_FIELDS)
        if staff is None:
            continue
        staff_parts = (*parts, "staff")
        check.ref_list(staff, "allergens", staff_parts, index.allergens, "allergen", required=False, allow_empty=True)
        tags = check.value(staff, "tags", "array", staff_parts)
        if tags is not MISSING:
            for position, tag in enumerate(tags):
                where = (*staff_parts, "tags", position)
                if not isinstance(tag, str) or not tag.strip() or "\n" in tag or "\r" in tag:
                    check.error(where, "must be a non-empty single-line string")
                else:
                    _braces(check, tag, where)
        _check_swaps(check, staff, staff_parts, index)
        _line(check, staff, "note", staff_parts)
    return dishes


def _check_sets(check: _Checker, menu: dict, index: MenuIndex) -> dict | None:
    sets = _registry(check, menu, "sets")
    for set_id, item in (sets or {}).items():
        parts = ("sets", set_id)
        item = check.object(item, parts)
        if item is None:
            continue
        check.unknown_fields(item, SET_FIELDS, parts)
        _line(check, item, "title", parts, required=True)
        for key in ("hint", "eyebrow", "pairing"):
            _line(check, item, key, parts)
        check.ref_list(item, "courses", parts, index.dishes, "dish", required=True, allow_empty=False)
    return sets


def _check_drinks(check: _Checker, menu: dict, index: MenuIndex) -> None:
    drinks = check.value(menu, "drinks", "object", ())
    if drinks is MISSING:
        if "drinks" not in menu:
            index.categories, index.drinks = {}, {}
        return
    parts = ("drinks",)
    check.unknown_fields(drinks, DRINKS_FIELDS, parts)
    index.categories = _registry(check, drinks, "categories", parts, required=True)
    for category_id, item in (index.categories or {}).items():
        item_parts = (*parts, "categories", category_id)
        item = check.object(item, item_parts)
        if item is not None:
            check.unknown_fields(item, CATEGORY_FIELDS, item_parts)
            _line(check, item, "label", item_parts, required=True)
    index.drinks = _registry(check, drinks, "items", parts, required=True)
    for drink_id, item in (index.drinks or {}).items():
        item_parts = (*parts, "items", drink_id)
        item = check.object(item, item_parts)
        if item is None:
            continue
        check.unknown_fields(item, DRINK_FIELDS, item_parts)
        if "category" not in item:
            check.error((*item_parts, "category"), "is required")
        else:
            check.ref(item["category"], (*item_parts, "category"), index.categories, "category")
        _line(check, item, "name", item_parts, required=True)
        _line(check, item, "details", item_parts)
        _line(check, item, "servedWith", item_parts)
        staff = _object(check, item, "staff", item_parts, DRINK_STAFF_FIELDS)
        if staff is not None:
            staff_parts = (*item_parts, "staff")
            _line(check, staff, "bottles", staff_parts)
            _line(check, staff, "serving", staff_parts)
            _check_swaps(check, staff, staff_parts, index)


def _section_id(check: _Checker, section: dict, parts: Sequence, positions: dict[str, int]) -> str | None:
    if "id" not in section:
        check.error((*parts, "id"), "is required")
    elif not is_identifier(section["id"]):
        check.error((*parts, "id"), f"must be an identifier: {ID_RULE}")
    elif section["id"] in positions:
        check.error(
            (*parts, "id"),
            f"repeats {show_id(section['id'])} (already used by sections[{positions[section['id']]}])",
        )
    else:
        positions[section["id"]] = parts[-1]
        return section["id"]
    return None


def _check_sections(check: _Checker, menu: dict, index: MenuIndex) -> None:
    sections = check.value(menu, "sections", "array", (), required=True)
    if sections is MISSING:
        index.sections_ok = False
        return
    if not sections:
        check.error(("sections",), "must list at least one section")
    seating = 0
    covers: list[int] = []
    positions: dict[str, int] = {}
    labels: dict[str, int] = {}  # a label of the line in lower case -> its section
    for position, section in enumerate(sections):
        parts = ("sections", position)
        section = check.object(section, parts)
        if section is None:
            index.sections_ok = False
            continue
        section_id = _section_id(check, section, parts, positions)
        if section_id is None:
            index.sections_ok = False
        kind = check.choice(section, "type", SECTION_TYPES, parts) if "type" in section else "custom"
        if kind is MISSING:
            index.sections_ok = False
            continue
        check.unknown_fields(section, SECTION_FIELDS[kind], parts)
        if section_id is not None:
            index.sections[section_id] = section
            index.widget_ids[section_id] = []
        if kind == "cover":
            if covers:
                check.error((*parts, "type"), "is 'cover': there may be only one cover")
            elif position != 0:
                check.error((*parts, "type"), "is 'cover': the cover must be the first section")
            covers.append(position)
            continue

        visible = check.value(section, "visible", "boolean", parts)
        audience = _audience(check.choice(section, "audience", AUDIENCES, parts))
        hidden_for_staff = audience == "staff" and visible is False
        if hidden_for_staff:
            check.warning((*parts, "visible"), _HIDDEN_STAFF_PART)
        widgets = check.value(section, "widgets", "array", parts, required=True)
        widgets = [] if widgets is MISSING else widgets
        has_seating = any(isinstance(widget, dict) and widget.get("type") == "seating" for widget in widgets)
        # default: a section with the seating widget may leave its title to the
        # page ("Your seat" for a guest, "Seating and dietary notes" for the staff)
        _line(check, section, "title", parts, required=not has_seating)
        _line(check, section, "eyebrow", parts)
        label = _line(check, section, "nav", parts)
        if isinstance(section.get("nav"), str) and not section["nav"].strip():
            # an empty text is "not set" elsewhere; a label is given or left out
            check.error((*parts, "nav"), f"must not be empty: {_NO_LABEL}")
        elif label is not MISSING:
            key = " ".join(label.split()).lower()
            if key in labels:
                check.warning(
                    (*parts, "nav"),
                    f"repeats the label of sections[{labels[key]}] in the line of the sections (letter case aside)",
                )
            else:
                labels[key] = position
        staff = _object(check, section, "staff", parts, SECTION_STAFF_FIELDS)
        if staff is not None:
            if audience == "guest":
                check.warning((*parts, "staff"), "has no effect: the section is for the guests only")
            for key in SECTION_STAFF_FIELDS:
                _line(check, staff, key, (*parts, "staff"))
        if audience == "staff":
            index.staff_parts.append(check.path(parts))
        kinds = []
        for number, widget in enumerate(widgets):
            kind_of_widget = _check_widget(
                check, widget, (*parts, "widgets", number), index, section_id, audience, hidden_for_staff
            )
            seating += kind_of_widget == "seating"
            kinds.append(kind_of_widget)
        _check_headings(check, kinds, parts)
    if seating > 1:
        check.error(("sections",), f"has {seating} seating widgets; there may be only one")
    if sections and not covers:
        check.warning(("sections",), "has no 'cover' section: the page will have no main heading")


def _check_headings(check: _Checker, kinds: list[str | None], parts: Sequence) -> None:
    """A heading needs something under it: a widget that is not a heading
    before the next heading.  The pages leave such a heading out."""
    for number, kind in enumerate(kinds):
        if kind != "heading":
            continue
        where = (*parts, "widgets", number)
        if number + 1 == len(kinds):
            check.warning(where, f"is a heading and the last widget of the section: {_EMPTY_HEADING}")
        elif kinds[number + 1] == "heading":
            check.warning(where, f"is a heading followed by another heading: {_EMPTY_HEADING}")


def _check_widget(
    check: _Checker,
    widget: Any,
    parts: Sequence,
    index: MenuIndex,
    section_id: str | None,
    section_audience: str,
    section_hidden: bool = False,
) -> str | None:
    """Check a widget; its type when it is usable.  `section_hidden`: the
    section is for the staff only and hidden (its widgets are reported with it)."""

    def broken() -> None:
        # the records may refer to this widget: their references to the
        # widgets of the section are not checked, the problem is reported here
        if section_id is not None:
            index.broken_widgets.add(section_id)

    widget = check.object(widget, parts)
    if widget is None:
        broken()
        return None
    if "type" not in widget:
        check.error((*parts, "type"), f"is required ({', '.join(WIDGET_TYPES)})")
        broken()
        return None
    kind = widget["type"]
    if kind not in WIDGET_TYPES:
        shown = f" {show_id(kind)}" if is_identifier(kind) else ""
        check.error(
            (*parts, "type"),
            f"names an unknown widget type{shown}{did_you_mean(kind, WIDGET_TYPES)}; "
            f"known: {', '.join(WIDGET_TYPES)}",
        )
        broken()
        return None
    check.unknown_fields(widget, WIDGET_BASE_FIELDS + WIDGET_FIELDS[kind], parts)
    visible = check.value(widget, "visible", "boolean", parts)
    audience = _audience(check.choice(widget, "audience", AUDIENCES, parts))
    compatible = section_audience == "all" or audience in ("all", section_audience)
    if not compatible:
        check.error((*parts, "audience"), f"is '{audience}' in a section for '{section_audience}': nobody sees it")
    effective = audience if audience != "all" else section_audience
    if effective == "staff" and visible is False and not section_hidden:
        check.warning((*parts, "visible"), _HIDDEN_STAFF_PART)
    if "id" in widget:
        widget_id = widget["id"]
        if not is_identifier(widget_id):
            check.error((*parts, "id"), f"must be an identifier: {ID_RULE}")
            broken()
        elif section_id is not None:
            if widget_id in index.widget_ids[section_id]:
                check.error((*parts, "id"), f"repeats {show_id(widget_id)} within the section")
            else:
                index.widget_ids[section_id].append(widget_id)
                index.widget_audience[(section_id, widget_id)] = effective
    if audience == "staff" and section_audience == "all":
        index.staff_parts.append(check.path(parts))

    staff_fields = WIDGET_STAFF_FIELDS.get(kind)
    if staff_fields:
        staff = _object(check, widget, "staff", parts, staff_fields)
        if staff is not None:
            if effective == "guest":
                check.warning((*parts, "staff"), "has no effect: the widget is for the guests only")
            for key in staff_fields:
                _line(check, staff, key, (*parts, "staff"))
    if kind in ("sets", "drinks"):
        _line(check, widget, "note", parts)
        if "note" in widget and effective == "staff":
            check.warning(
                (*parts, "note"),
                "has no effect: the note is shown to the guests, and the widget is for the staff only "
                "(the staff page shows 'staff.note')",
            )

    if kind == "text":
        _text(check, widget, "text", parts, required=True)
        check.choice(widget, "variant", TEXT_VARIANTS, parts)
    elif kind == "seating":
        for key in ("showScheme", "showLegend", "showTable"):
            check.value(widget, key, "boolean", parts)
    elif kind == "dishes":
        check.ref_list(widget, "items", parts, index.dishes, "dish", required=True, allow_empty=False)
        _line(check, widget, "title", parts)
    elif kind == "sets":
        check.ref_list(widget, "items", parts, index.sets, "set", required=True, allow_empty=False)
    elif kind == "heading":
        _line(check, widget, "title", parts, required=True)
        _line(check, widget, "eyebrow", parts)
    elif kind == "drinks":
        groups = check.value(widget, "groups", "array", parts, required=True)
        if groups is not MISSING:
            if not groups:
                check.error((*parts, "groups"), "must list at least one group")
            for position, group in enumerate(groups):
                group_parts = (*parts, "groups", position)
                group = check.object(group, group_parts)
                if group is None:
                    continue
                check.unknown_fields(group, GROUP_FIELDS, group_parts)
                _line(check, group, "title", group_parts)
                check.choice(group, "layout", GROUP_LAYOUTS, group_parts)
                check.ref_list(group, "items", group_parts, index.drinks, "drink", required=True, allow_empty=False)
    return kind


# --------------------------------------------------------------------------
# guests.json
# --------------------------------------------------------------------------


def check_guests(guests: Any, index: MenuIndex, menu: dict, report: Any) -> None:
    """Check `guests.json` against what `check_menu` found (`index` is
    completed: the taken seats, their requirements, the staff record).

    The number of errors is kept in `index.guest_errors`.
    """
    checkers: list[_Checker] = []
    try:
        _check_guests(guests, index, menu, report, checkers)
    finally:
        index.guest_errors = sum(check.errors for check in checkers)
    _after_records(index, menu, report, guests)


def _check_guests(guests: Any, index: MenuIndex, menu: dict, report: Any, checkers: list[_Checker]) -> None:
    top = _Checker(report, GUESTS_FILE)
    checkers.append(top)
    if not isinstance(guests, list):
        top.raw_error(f"the top-level value must be an array of records, got {json_type(guests)}")
        return
    if not guests:
        top.warning((), "contains no records")
        return
    known = guest_known(index)
    seen: dict[str, int] = {}
    for number, record in enumerate(guests, start=1):
        if not isinstance(record, dict):
            top.errors += 1
            report.error(f"{guest_where(number)}: must be an object, got {json_type(record)}")
            continue
        check = _Checker(report, guest_where(number), known)
        checkers.append(check)
        _check_token(check, record, number, seen)
        if "staff" in record:
            _check_staff_record(check, record, number, index)
            continue
        index.guests += 1
        check.unknown_fields(record, GUEST_FIELDS, ())
        _line(check, record, "name", (), required=True)
        _check_seats(check, record, number, index, menu)
        _check_overrides(check, record, index)
    if not index.staff_claimed:
        top.warning((), "has no staff record ('staff': true): no staff page is built")
        if index.staff_parts:
            _Checker(report, MENU_FILE).warning(
                ("sections",),
                f"has parts for the staff only ({', '.join(index.staff_parts)}), but there is no staff record",
            )


def _check_token(check: _Checker, record: dict, number: int, seen: dict[str, int]) -> None:
    if "token" not in record:
        check.error(("token",), "is required")
        return
    problem = check_token(record["token"])
    if problem:
        check.raw_error(problem)
        return
    key = record["token"].lower()
    if key in seen:
        check.raw_error(
            f"duplicate token (same as {guest_label(seen[key])}; tokens are compared "
            "case-insensitively because they become directory names)"
        )
    else:
        seen[key] = number


def _check_staff_record(check: _Checker, record: dict, number: int, index: MenuIndex) -> None:
    index.staff_claimed = True
    if record["staff"] is not True:
        check.error(("staff",), "must be true (leave the field out for a guest)")
        return
    hints = {name: _STAFF_ONLY_HINT for name in GUEST_FIELDS if name != "token"}
    check.unknown_fields(record, STAFF_RECORD_FIELDS, (), hints)
    if index.staff_record:
        check.raw_error(
            f"is a second staff record (the first is {guest_label(index.staff_record)}); there may be only one"
        )
        return
    index.staff_record = number
    token = record.get("token")
    if isinstance(token, str) and check_token(token) is None and len(token) < STAFF_TOKEN_MIN:
        check.warning(
            ("token",),
            f"is shorter than {STAFF_TOKEN_MIN} characters: the staff page shows every name and "
            f"dietary note; use a random token of at least {STAFF_TOKEN_MIN} characters",
        )


def _adjacent(first: int, second: int, total: int) -> bool:
    """Neighbours on the table plan: the numbers go round, N and 1 meet."""
    return abs(first - second) == 1 or {first, second} == {1, total}


def _check_seats(check: _Checker, record: dict, number: int, index: MenuIndex, menu: dict) -> None:
    seats = check.value(record, "seats", "array", (), required=True)
    if seats is MISSING:
        return
    if not seats:
        check.error(("seats",), "must list at least one seat (the guest's own seat comes first)")
        return
    colours = len(_table.SEAT_COLOURS)
    if len(seats) > colours:
        check.error(
            ("seats",),
            f"lists {len(seats)} seats, at most {colours} are allowed: the page of a guest marks each seat "
            "of the record in a colour of its own (split the record in two)",
        )
    label = guest_label(number)
    own: dict[int, int] = {}  # seat -> position in this record
    first: int | None = None
    for position, seat in enumerate(seats):
        parts = ("seats", position)
        seat = check.object(seat, parts)
        if seat is None:
            continue
        check.unknown_fields(seat, SEAT_FIELDS, parts)
        plus_one = check.value(seat, "plusOne", "boolean", parts)
        if plus_one is True and position == 0:
            check.error((*parts, "plusOne"), "cannot be set on the first seat: it is the guest's own seat")
        _line(check, seat, "name", parts)
        if position > 0 and plus_one is not True and _blank(seat.get("name")):
            check.error((*parts, "name"), "is required for a seat that is not a +1 ('plusOne': true)")
        found = check.ref_list(
            seat, "requirements", parts, index.requirements, "requirement", required=False, allow_empty=True
        )
        seat_number = check.value(seat, "number", "count", parts, required=True)
        where = (*parts, "number")
        if seat_number is MISSING or not _in_range(check, seat_number, where, index):
            continue
        shown = _seat_text(seat_number, index)
        if seat_number in own:
            check.error(where, f"refers to {shown}, already taken by this guest (seats[{own[seat_number]}])")
            continue
        if seat_number in index.reserved:
            check.error(where, f"refers to {shown}, which is reserved ('reservedSeats')")
            continue
        if seat_number in index.taken:
            check.error(where, f"refers to {shown}, already taken by {index.taken[seat_number]}")
            continue
        own[seat_number] = position
        index.taken[seat_number] = label
        index.seat_requirements[seat_number] = list(found or [])
        _badges(check, menu, index, seat_number, found or [], (*parts, "requirements"))
        if position == 0:
            first = seat_number
        elif plus_one is True and first is not None and index.table_ok and index.total:
            if not _adjacent(first, seat_number, index.total):
                check.warning(
                    where,
                    f"is a +1 seat that is not next to the guest's own seat {first} on the table plan",
                )


def _check_overrides(check: _Checker, record: dict, index: MenuIndex) -> None:
    overrides = check.value(record, "sections", "object", ())
    if overrides is MISSING:
        return
    for section_id, override in overrides.items():
        parts = ("sections", section_id)
        section = index.sections.get(section_id)
        if section is None:
            if index.sections_ok:  # else it may be one of the broken sections
                check.error(
                    parts,
                    f"refers to an unknown section{did_you_mean(section_id, index.sections)}"
                    f"{_known_list(index.sections, 'section')}",
                )
            continue
        override = check.object(override, parts)
        if override is None:
            continue
        if section.get("type") == "cover":
            check.error(parts, "cannot be set: the cover is the same for everybody")
            continue
        if section.get("audience") == "staff":
            check.error(parts, "refers to a section for the staff only: a guest never sees it")
            continue
        check.unknown_fields(override, GUEST_SECTION_FIELDS, parts)
        shown = check.value(override, "visible", "boolean", parts)
        note = _text(check, override, "note", parts)
        visible = shown if shown is not MISSING else section.get("visible") is not False
        if not visible and note is not MISSING:
            check.warning((*parts, "note"), "is set, but the section is hidden for this guest")
        widgets = check.value(override, "widgets", "object", parts)
        if widgets is MISSING:
            continue
        declared = index.widget_ids.get(section_id, [])
        for widget_id, widget_override in widgets.items():
            widget_parts = (*parts, "widgets", widget_id)
            if widget_id not in declared:
                if section_id in index.broken_widgets:
                    continue  # it may be the broken widget, reported in menu.json
                hint = (
                    f"{did_you_mean(widget_id, declared)}; widgets with an id: {', '.join(declared)}"
                    if declared
                    else '; give the widget an "id" in menu.json to address it'
                )
                check.error(widget_parts, f"refers to no widget of section {show_id(section_id)}{hint}")
                continue
            if index.widget_audience.get((section_id, widget_id)) == "staff":
                check.error(widget_parts, "refers to a widget for the staff only: a guest never sees it")
                continue
            widget_override = check.object(widget_override, widget_parts)
            if widget_override is not None:
                check.unknown_fields(widget_override, GUEST_WIDGET_FIELDS, widget_parts)
                check.value(widget_override, "visible", "boolean", widget_parts)


def _after_records(index: MenuIndex, menu: dict, report: Any, guests: Any) -> None:
    """Warnings about `menu.json` that need the records.

    They follow from the seats and references of both files, so they are
    left out while either file has an error: a seat moved by mistake or a
    misspelt requirement would show up twice, as its error and as a free
    seat or an unused requirement.
    """
    if not isinstance(guests, list) or not guests or index.errors or index.guest_errors:
        return
    check = _Checker(report, MENU_FILE)
    if index.table_ok and index.total:
        free = [
            number for number in range(1, index.total + 1)
            if number not in index.taken and number not in index.reserved
        ]
        if free:
            listed = ", ".join(str(number) for number in free)
            check.warning(
                ("table", "seats"),
                f"has {len(free)} free seat(s): {listed} (shown as free on the staff page; "
                "list a seat that stays free on purpose in 'reservedSeats')",
            )
    used = {requirement for items in index.seat_requirements.values() for requirement in items}
    for requirement_id in index.requirements or {}:
        if requirement_id not in used:
            check.warning(("requirements", requirement_id), "is not used by any seat; it is left out of the legend")
    contained: set[str] = set()
    for dish in (index.dishes or {}).values():
        staff = dish.get("staff") if isinstance(dish, dict) else None
        if isinstance(staff, dict) and isinstance(staff.get("allergens"), list):
            contained.update(item for item in staff["allergens"] if isinstance(item, str))
    for requirement in (index.requirements or {}).values():
        if isinstance(requirement, dict) and isinstance(requirement.get("avoids"), list):
            contained.update(item for item in requirement["avoids"] if isinstance(item, str))
    for allergen_id in index.allergens or {}:
        if allergen_id not in contained:
            check.warning(("allergens", allergen_id), "is not used by any dish or requirement")


def check_data(menu: Any, guests: Any, report: Any) -> MenuIndex:
    """Check both documents (`guests.json` only when `menu.json` has a
    supported version: the records refer to it)."""
    index = check_menu(menu, report)
    if index.version_ok:
        check_guests(guests, index, menu, report)
    return index


# --------------------------------------------------------------------------
# What the pages show
# --------------------------------------------------------------------------


def check_usage(index: MenuIndex, menu: dict, usage: Any, report: Any) -> None:
    """Warnings that need the finished page trees.

    `usage` tells what the pages show, as sets of ids: `dishes`, `sets` and
    `drinks` on any page (a guest page or the staff page, built even when
    there is no staff record), `staff_dishes` on the staff page.
    """
    check = _Checker(report, MENU_FILE)
    for name, registry, shown in (
        (("dishes",), index.dishes, usage.dishes),
        (("sets",), index.sets, usage.sets),
        (("drinks", "items"), index.drinks, usage.drinks),
    ):
        for item_id in registry or {}:
            if item_id not in shown:
                check.warning((*name, item_id), "is not shown on any page")
    if not index.allergens:
        return
    # a dish the staff page shows, an allergen in it that a requirement
    # avoids, a seat with that requirement and no swap: the waiter would get
    # no instruction
    seats_of: dict[str, int] = {}
    for items in index.seat_requirements.values():
        for requirement_id in items:
            seats_of[requirement_id] = seats_of.get(requirement_id, 0) + 1
    for dish_id, dish in (index.dishes or {}).items():
        if dish_id not in usage.staff_dishes:
            continue
        staff = dish.get("staff") if isinstance(dish.get("staff"), dict) else {}
        if "allergens" not in staff:
            check.warning(
                ("dishes", dish_id, "staff", "allergens"),
                "is not set: the staff page shows no allergen information for the dish (write [] for none)",
            )
            continue
        contains = set(staff["allergens"])
        swaps = staff.get("swaps") if isinstance(staff.get("swaps"), dict) else {}
        for requirement_id, requirement in (index.requirements or {}).items():
            avoided = set(requirement.get("avoids") or [])
            seats = seats_of.get(requirement_id, 0)
            if seats and avoided & contains and requirement_id not in swaps:
                check.warning(
                    ("dishes", dish_id, "staff", "swaps"),
                    f"has no swap for {show_id(requirement_id)}, while the dish holds an allergen it "
                    f"avoids and {seats} seat(s) need it",
                )


__all__ = [
    "SCHEMA_VERSION",
    "MENU_FILE",
    "GUESTS_FILE",
    "AUDIENCES",
    "MenuIndex",
    "check_menu",
    "check_guests",
    "check_data",
    "check_usage",
    "guest_known",
    "guest_label",
    "guest_where",
]
