"""Page trees of the menu: one per guest record and one for the staff.

A tree is what the template and its fragments render: plain dicts, lists,
strings, numbers and booleans, in which every field always exists (`""`,
`[]`, `false`, `0` or `null` when there is nothing to show).  The data must
have passed the checks in `menu_tools._schema`.

Privacy by construction.  A guest page is built from two projections only:
`public_menu` (the shared texts outside the `staff` keys and the staff-only
parts, the names and ingredients of the dishes guests see, their sets, the
guest fields of their drinks, the table) and `own_record` (the name, the
seat numbers, which of them a companion takes, the seat names, the section
switches and notes).  The record's seat names appear in the names under the
plan (`names`) and in the plan's text (`scheme.mine`), nowhere else on the
page.  Tokens, other records, requirements, allergens, the couple and the
names at other seats never reach the code that builds a guest page.  The
staff page reads the whole menu and the records without their tokens and
notes.  No page holds a token: a record's token names its page directory
and nothing else.

A guest page names no seat by its number: its table plan shows the
record's seats each in a colour of its own (`_table.SEAT_COLOURS`), and the
names under the plan use the same colours, in the order of the record's
seats.

The navigation bar at the top of a page (`nav` in the root) links the
page's sections that have a label (a section's `nav`), in page order: a
section the page does not show has no link there.

A heading widget heads a part of its section: the widgets after it on the
same page, up to the next heading.  A heading with no other widget under it
on a page is left out of that page, so a section that keeps only headings
is empty there.  A guest page shows a heading's texts outside its `staff`
key; the staff page shows those under it when they are set.  A set card
under a heading uses the next heading level (`nested`), and the heading
labels its tab list.

The words joined with numbers and names come from `menu_tools._words`; the
table scheme is built by `menu_tools._table` (`guest_scheme`,
`staff_scheme`).

Standard library only; no input/output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

from menu_tools import _table, _words
from menu_tools._schema import EVENT_FIELDS, MENU_FILE, guest_where

DEFAULT_VARIANT = "body"
DEFAULT_LAYOUT = "list"
INLINE_LAYOUT = "inline"
#: The widget that heads a part of a section.
HEADING = "heading"
STAFF_FIELDS = ("updated", "contact", "reminder")


class Settings(NamedTuple):
    """What a tree takes from the build: the address of the shared files
    (`<base path>/assets`) and the browser interface colour."""

    assets_path: str = "/assets"
    theme_color: str = ""


DEFAULT_SETTINGS = Settings()


class Page(NamedTuple):
    """The tree of one page and the record it belongs to."""

    #: The record's position in `guests.json`, from 1.
    number: int
    #: The page directory.
    token: str
    tree: dict


@dataclass
class Usage:
    """The ids of what the pages show (the staff page counts even when there
    is no staff record: it shows what the staff would see)."""

    dishes: set[str] = field(default_factory=set)
    sets: set[str] = field(default_factory=set)
    drinks: set[str] = field(default_factory=set)
    #: The dishes the staff page shows.
    staff_dishes: set[str] = field(default_factory=set)


class Trees(NamedTuple):
    #: The guest pages, in `guests.json` order.
    guests: list[Page]
    #: The staff page; None without a staff record.
    staff: Page | None
    usage: Usage


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _text(value: Any) -> str:
    """A text of the data, or "" when it is absent or empty."""
    return value if isinstance(value, str) and value.strip() else ""


def _audience(item: dict) -> str:
    return item.get("audience", "all")


def _root(source: dict, settings: Settings, *, is_staff: bool) -> dict:
    return {
        "isStaff": is_staff,
        "coupleNames": source["coupleNames"],
        "event": {key: source["event"][key] for key in EVENT_FIELDS},
        "assetsPath": settings.assets_path,
        "faviconPath": f"{settings.assets_path}/favicon.svg",
        "themeColor": settings.theme_color,
        "staff": {key: "" for key in STAFF_FIELDS},
        "counters": {"guests": 0, "notes": 0, "guestsText": "", "notesText": "", "tableLabel": ""},
        "nav": [],
        "sections": [],
    }


def _add_section(root: dict, built: dict | None, label: str) -> None:
    """A section of the page and, with a label, its link in the navigation bar."""
    if built is None:
        return
    root["sections"].append(built)
    if label:
        root["nav"].append({"label": label, "target": built["domId"]})


def _section(section_id: str, kind: str) -> dict:
    dom_id = f"s-{section_id}"
    return {
        "id": section_id,
        "type": kind,
        "domId": dom_id,
        "titleId": f"{dom_id}--title",
        "title": "",
        "eyebrow": "",
        "note": "",
        "widgets": [],
    }


def _dish(dish: dict) -> dict:
    """A dish as the guests see it; the staff fields are empty."""
    return {
        "name": dish["name"],
        "ingredients": _text(dish.get("ingredients")),
        "allergens": [],
        "tags": "",
        "noRestrictions": False,
        "swapLines": [],
        "note": "",
    }


def _set(
    set_id: str, item: dict, widget_dom_id: str, courses: list[dict], swap_lines: list[str], nested: bool
) -> dict:
    """A set card; `nested`: it stands under a part's heading (its own title
    is a level lower).  Every card carries the flag, since the fragment reads
    the cards, not the widget."""
    return {
        "id": set_id,
        "domId": f"{widget_dom_id}--set-{set_id}",
        "title": item["title"],
        "hint": _text(item.get("hint")),
        "eyebrow": _text(item.get("eyebrow")),
        "courses": courses,
        "pairing": _text(item.get("pairing")),
        "swapLines": swap_lines,
        "nested": nested,
    }


def _parts(shown: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """The widgets of a section that a page shows, as (position in the data,
    widget) in order, without headings that have nothing under them: a
    heading followed by another heading or by the end of the section."""
    kept = []
    for at, (position, widget) in enumerate(shown):
        if widget["type"] == HEADING:
            following = shown[at + 1][1] if at + 1 < len(shown) else None
            if following is None or following["type"] == HEADING:
                continue
        kept.append((position, widget))
    return kept


def _heading(base: dict, title: str, eyebrow: str) -> dict:
    return {**base, "titleId": f"{base['domId']}--title", "title": title, "eyebrow": eyebrow}


def _seating(base: dict) -> dict:
    """A seating widget with every field empty."""
    return {
        **base,
        "scheme": None,
        "names": [],
        "legend": [],
        "rows": [],
        "footnote": "",
    }


def _couple(couple: dict) -> dict:
    """The couple as the table plan needs it: label, arm and seats."""
    return {
        "couple_seats": [member["seat"] for member in couple.get("members", [])],
        "couple_label": _text(couple.get("label")) or None,
        "couple_arm": _text(couple.get("arm")) or None,
    }


# --------------------------------------------------------------------------
# What a guest page is built from
# --------------------------------------------------------------------------


def public_menu(menu: dict) -> dict:
    """The part of the menu every guest page is built from.

    Staff-only sections and widgets are left out (a widget keeps its place
    as None: a section's widgets are numbered by their position in the
    data); so are the `staff` keys, the requirements, the allergens, the
    couple (a guest's plan does not show it), the dish, set and drink fields
    a guest does not see, and every dish, set or drink that no part for the
    guests refers to.
    """
    public: dict[str, Any] = {
        "coupleNames": menu["coupleNames"],
        "event": {key: menu["event"][key] for key in EVENT_FIELDS},
        "table": menu.get("table"),
        "dishes": {},
        "sets": {},
        "drinks": {},
        "categories": {},
        "sections": [],
    }
    for section in menu["sections"]:
        if section.get("type") == "cover":
            public["sections"].append({"id": section["id"], "type": "cover"})
            continue
        if _audience(section) == "staff":
            continue
        widgets: list[dict | None] = []
        for widget in section["widgets"]:
            widgets.append(None if _audience(widget) == "staff" else _public_widget(menu, widget, public))
        public["sections"].append({
            "id": section["id"],
            "type": "custom",
            "visible": section.get("visible", True),
            "title": _text(section.get("title")),
            "eyebrow": _text(section.get("eyebrow")),
            "nav": _text(section.get("nav")),
            "widgets": widgets,
        })
    return public


def _public_widget(menu: dict, widget: dict, public: dict) -> dict:
    kind = widget["type"]
    item: dict[str, Any] = {"type": kind, "id": widget.get("id"), "visible": widget.get("visible", True)}
    if kind == "text":
        item.update(text=widget["text"], variant=widget.get("variant", DEFAULT_VARIANT))
    elif kind == HEADING:
        item.update(title=widget["title"], eyebrow=_text(widget.get("eyebrow")))
    elif kind == "seating":
        item["showScheme"] = widget.get("showScheme", True)
    elif kind == "dishes":
        item.update(items=list(widget["items"]), title=_text(widget.get("title")))
        for dish_id in widget["items"]:
            _public_dish(menu, dish_id, public)
    elif kind == "sets":
        item.update(items=list(widget["items"]), note=_text(widget.get("note")))
        for set_id in widget["items"]:
            entry = menu["sets"][set_id]
            public["sets"][set_id] = {
                "title": entry["title"],
                "hint": _text(entry.get("hint")),
                "eyebrow": _text(entry.get("eyebrow")),
                "pairing": _text(entry.get("pairing")),
                "courses": list(entry["courses"]),
            }
            for dish_id in entry["courses"]:
                _public_dish(menu, dish_id, public)
    elif kind == "drinks":
        groups = []
        for group in widget["groups"]:
            groups.append({
                "title": _text(group.get("title")),
                "layout": group.get("layout", DEFAULT_LAYOUT),
                "items": list(group["items"]),
            })
            for drink_id in group["items"]:
                drink = menu["drinks"]["items"][drink_id]
                public["drinks"][drink_id] = {
                    "category": drink["category"],
                    "name": drink["name"],
                    "details": _text(drink.get("details")),
                    "servedWith": _text(drink.get("servedWith")),
                }
                category = menu["drinks"]["categories"][drink["category"]]
                public["categories"][drink["category"]] = {"label": category["label"]}
        item.update(groups=groups, note=_text(widget.get("note")))
    return item


def _public_dish(menu: dict, dish_id: str, public: dict) -> None:
    dish = menu["dishes"][dish_id]
    public["dishes"][dish_id] = {"name": dish["name"], "ingredients": _text(dish.get("ingredients"))}


def own_record(record: dict) -> dict:
    """The part of a record its own page is built from.

    The token and the seat requirements are left out: a guest page shows
    neither.  A seat's `name` is its name ("" without one): the names under
    the plan show who sits at which of the record's seats.
    """
    sections = {}
    for section_id, override in (record.get("sections") or {}).items():
        sections[section_id] = {
            "visible": override.get("visible"),
            "note": _text(override.get("note")),
            "widgets": {
                widget_id: switch.get("visible")
                for widget_id, switch in (override.get("widgets") or {}).items()
            },
        }
    return {
        "name": record["name"],
        "seats": [
            {
                "number": seat["number"],
                "plusOne": seat.get("plusOne") is True,
                "name": _text(seat.get("name")),
            }
            for seat in record["seats"]
        ],
        "sections": sections,
    }


# --------------------------------------------------------------------------
# A guest page
# --------------------------------------------------------------------------


class _GuestPage:
    """The tree of one guest's page, from `public_menu` and `own_record`."""

    def __init__(self, public: dict, own: dict, settings: Settings, usage: Usage):
        self.public = public
        self.own = own
        self.settings = settings
        self.usage = usage

    def tree(self) -> dict:
        root = _root(self.public, self.settings, is_staff=False)
        for section in self.public["sections"]:
            _add_section(root, self.section(section), section.get("nav", ""))
        return root

    def section(self, section: dict) -> dict | None:
        tree = _section(section["id"], section["type"])
        if section["type"] == "cover":
            return tree
        override = self.own["sections"].get(section["id"], {})
        visible = override.get("visible")
        if not (section["visible"] if visible is None else visible):
            return None
        switches = override.get("widgets", {})
        shown = []
        for position, widget in enumerate(section["widgets"], start=1):
            if widget is None:
                continue
            switch = switches.get(widget["id"]) if widget["id"] is not None else None
            if widget["visible"] if switch is None else switch:
                shown.append((position, widget))
        heading = None  # the title of the part the widgets stand in
        for position, widget in _parts(shown):
            dom_id = f"{tree['domId']}--w{position}"
            if widget["type"] == HEADING:
                heading = f"{dom_id}--title"
            tree["widgets"].append(self.widget(widget, dom_id, tree["titleId"], heading))
        tree["note"] = override.get("note", "")
        if not tree["widgets"] and not tree["note"]:
            return None
        has_seating = any(widget is not None and widget["type"] == "seating" for widget in section["widgets"])
        default = _words.section_title(len(self.own["seats"])) if has_seating else ""
        tree["title"] = section["title"] or default
        tree["eyebrow"] = section["eyebrow"]
        return tree

    def widget(self, widget: dict, dom_id: str, labelled_by: str, heading: str | None = None) -> dict:
        """A widget's node; `heading`: the title id of the part it stands
        in, None outside a part."""
        kind = widget["type"]
        base = {"type": kind, "domId": dom_id, "labelledBy": labelled_by}
        public = self.public
        if kind == "text":
            return {**base, "text": widget["text"], "variant": widget["variant"]}
        if kind == HEADING:
            return _heading(base, widget["title"], widget["eyebrow"])
        if kind == "seating":
            return self.seating(widget, base)
        if kind == "dishes":
            self.usage.dishes.update(widget["items"])
            items = [_dish(public["dishes"][dish_id]) for dish_id in widget["items"]]
            return {**base, "title": widget["title"], "items": items}
        if kind == "sets":
            items = []
            for set_id in widget["items"]:
                entry = public["sets"][set_id]
                self.usage.sets.add(set_id)
                self.usage.dishes.update(entry["courses"])
                courses = [_dish(public["dishes"][dish_id]) for dish_id in entry["courses"]]
                items.append(_set(set_id, entry, dom_id, courses, [], heading is not None))
            return {**base, "labelledBy": heading or labelled_by, "items": items, "note": widget["note"],
                    "multiple": len(items) > 1}
        if kind == "drinks":
            groups = []
            for group in widget["groups"]:
                self.usage.drinks.update(group["items"])
                drinks = [public["drinks"][drink_id] for drink_id in group["items"]]
                inline = group["layout"] == INLINE_LAYOUT
                groups.append({
                    "title": group["title"],
                    "layout": group["layout"],
                    "joined": _words.listed(drink["name"] for drink in drinks) if inline else "",
                    "items": [] if inline else [
                        {
                            "category": public["categories"][drink["category"]]["label"],
                            "name": drink["name"],
                            "line": _words.joined([drink["details"], drink["servedWith"]]),
                        }
                        for drink in drinks
                    ],
                })
            return {**base, "groups": groups, "list": [], "note": widget["note"]}
        raise ValueError(f"unknown widget type: {kind}")  # pragma: no cover - checked data

    def seating(self, widget: dict, base: dict) -> dict:
        """The record's seats: a name per seat, coloured by the seat's place
        in the record, and the plan with the seats in those colours."""
        seats = self.own["seats"]
        numbers = [seat["number"] for seat in seats]
        names = _words.seat_names(self.own["name"], [seat["name"] for seat in seats])
        tree = _seating(base)
        # checked data: a record has no more seats than there are colours
        tree["names"] = [
            {"name": name, "colour": _table.SEAT_COLOURS[position]} for position, name in enumerate(names)
        ]
        table = self.public["table"]
        if table is not None and widget["showScheme"]:
            tree["scheme"] = _table.guest_scheme(table, own_seats=numbers, mine_text=_words.colour_key(names))
        return tree


# --------------------------------------------------------------------------
# The staff page
# --------------------------------------------------------------------------


class _StaffPage:
    """The staff page tree: the whole menu, every seat, no token and no
    guest's note."""

    def __init__(self, menu: dict, records: list, settings: Settings, usage: Usage):
        self.menu = menu
        self.settings = settings
        self.usage = usage
        self.requirements = menu.get("requirements") or {}
        order = {requirement_id: position for position, requirement_id in enumerate(self.requirements)}

        def legend_order(items: list) -> list:
            return sorted(items, key=lambda requirement_id: order[requirement_id])

        #: seat -> who sits there
        self.occupants: dict[int, dict] = {}
        for member in (menu.get("couple") or {}).get("members", []):
            self.occupants[member["seat"]] = {
                "name": member["name"],
                "roleLabel": _text(member.get("role")),
                "isCouple": True,
                "isPlusOne": False,
                "hostName": "",
                "requirements": legend_order(member.get("requirements", [])),
            }
        # default: the staff sees what at least one guest sees, plus the
        # staff-only parts: a section or widget hidden by default but
        # switched on for one guest is served too
        self.switched_sections: set[str] = set()
        self.switched_widgets: set[tuple[str, str]] = set()
        for record in records:
            if record.get("staff") is True:
                continue
            seats = record["seats"]
            host = _text(seats[0].get("name")) or record["name"]
            for position, seat in enumerate(seats):
                plus_one = seat.get("plusOne") is True
                name = _text(seat.get("name"))
                self.occupants[seat["number"]] = {
                    "name": name if name or plus_one or position else record["name"],
                    "roleLabel": "",
                    "isCouple": False,
                    "isPlusOne": plus_one,
                    "hostName": host if plus_one else "",
                    "requirements": legend_order(seat.get("requirements", [])),
                }
            for section_id, override in (record.get("sections") or {}).items():
                if override.get("visible") is True:
                    self.switched_sections.add(section_id)
                for widget_id, switch in (override.get("widgets") or {}).items():
                    if switch.get("visible") is True:
                        self.switched_widgets.add((section_id, widget_id))
        #: requirement -> the seats that have it, in ascending order
        self.seats_of: dict[str, list[int]] = {}
        for number in sorted(self.occupants):
            for requirement_id in self.occupants[number]["requirements"]:
                self.seats_of.setdefault(requirement_id, []).append(number)

    def tree(self) -> dict:
        menu = self.menu
        root = _root(menu, self.settings, is_staff=True)
        staff = menu.get("staff") or {}
        root["staff"] = {key: _text(staff.get(key)) for key in STAFF_FIELDS}
        guests = len(self.occupants)
        notes = sum(1 for occupant in self.occupants.values() if occupant["requirements"])
        table = menu.get("table")
        root["counters"] = {
            "guests": guests,
            "notes": notes,
            "guestsText": _words.guests_text(guests),
            "notesText": _words.notes_text(notes),
            "tableLabel": table["label"] if table else "",
        }
        for section in menu["sections"]:
            _add_section(root, self.section(section), _text(section.get("nav")))
        return root

    def section(self, section: dict) -> dict | None:
        tree = _section(section["id"], section.get("type", "custom"))
        if tree["type"] == "cover":
            return tree
        if _audience(section) == "guest":
            return None
        if section.get("visible", True) is False and section["id"] not in self.switched_sections:
            return None
        shown = []
        for position, widget in enumerate(section["widgets"], start=1):
            if _audience(widget) == "guest":
                continue
            switched = (section["id"], widget.get("id")) in self.switched_widgets
            if widget.get("visible", True) is False and not switched:
                continue
            shown.append((position, widget))
        heading = None  # the title of the part the widgets stand in
        for position, widget in _parts(shown):
            dom_id = f"{tree['domId']}--w{position}"
            if widget["type"] == HEADING:
                heading = f"{dom_id}--title"
            tree["widgets"].append(self.widget(widget, dom_id, tree["titleId"], heading))
        if not tree["widgets"]:
            return None
        staff = section.get("staff") or {}
        has_seating = any(_audience(widget) != "guest" and widget["type"] == "seating" for widget in section["widgets"])
        tree["title"] = (
            _text(staff.get("title")) or _text(section.get("title")) or (_words.STAFF_SEATING if has_seating else "")
        )
        tree["eyebrow"] = _text(staff.get("eyebrow")) or _text(section.get("eyebrow"))
        return tree

    def widget(self, widget: dict, dom_id: str, labelled_by: str, heading: str | None = None) -> dict:
        """A widget's node; `heading`: the title id of the part it stands
        in, None outside a part."""
        kind = widget["type"]
        base = {"type": kind, "domId": dom_id, "labelledBy": labelled_by}
        menu = self.menu
        staff = widget.get("staff") or {}
        if kind == "text":
            return {**base, "text": widget["text"], "variant": widget.get("variant", DEFAULT_VARIANT)}
        if kind == HEADING:
            return _heading(
                base,
                _text(staff.get("title")) or widget["title"],
                _text(staff.get("eyebrow")) or _text(widget.get("eyebrow")),
            )
        if kind == "seating":
            return self.seating(widget, base)
        if kind == "dishes":
            items = []
            for dish_id in widget["items"]:
                item = self.dish(dish_id)
                swaps = (menu["dishes"][dish_id].get("staff") or {}).get("swaps") or {}
                item["swapLines"] = [_words.dish_swap_line(seats, text) for seats, _id, text in self.swaps(swaps)]
                items.append(item)
            self.usage.dishes.update(widget["items"])
            self.usage.staff_dishes.update(widget["items"])
            return {**base, "title": _text(widget.get("title")), "items": items}
        if kind == "sets":
            items = []
            for set_id in widget["items"]:
                entry = menu["sets"][set_id]
                found = []
                for dish_id in entry["courses"]:
                    found += self.swaps((menu["dishes"][dish_id].get("staff") or {}).get("swaps") or {})
                found.sort(key=lambda swap: swap[0][0])
                lines = [
                    _words.set_swap_line(seats, self.requirements[requirement_id]["label"], text, first=position == 0)
                    for position, (seats, requirement_id, text) in enumerate(found)
                ]
                courses = [self.dish(dish_id) for dish_id in entry["courses"]]
                items.append(_set(set_id, entry, dom_id, courses, lines, heading is not None))
                self.usage.sets.add(set_id)
                self.usage.dishes.update(entry["courses"])
                self.usage.staff_dishes.update(entry["courses"])
            note = _text(staff.get("note"))
            return {**base, "labelledBy": heading or labelled_by, "items": items, "note": note,
                    "multiple": len(items) > 1}
        if kind == "drinks":
            listed = []
            drinks = menu["drinks"]
            for group in widget["groups"]:
                for drink_id in group["items"]:
                    drink = drinks["items"][drink_id]
                    drink_staff = drink.get("staff") or {}
                    reminders = [
                        _words.drink_reminder(seats, text)
                        for seats, _id, text in self.swaps(drink_staff.get("swaps") or {})
                    ]
                    listed.append({
                        "category": drinks["categories"][drink["category"]]["label"],
                        "name": drink["name"],
                        "line": _words.joined([
                            _text(drink.get("servedWith")),
                            _text(drink_staff.get("bottles")),
                            _text(drink_staff.get("serving")),
                            *reminders,
                        ]),
                    })
                self.usage.drinks.update(group["items"])
            return {**base, "groups": [], "list": listed, "note": _text(staff.get("note"))}
        raise ValueError(f"unknown widget type: {kind}")  # pragma: no cover - checked data

    def dish(self, dish_id: str) -> dict:
        dish = self.menu["dishes"][dish_id]
        item = _dish(dish)
        staff = dish.get("staff") or {}
        allergens = self.menu.get("allergens") or {}
        tags = staff.get("tags") or []
        item["allergens"] = [allergens[allergen_id]["label"] for allergen_id in staff.get("allergens", [])]
        item["tags"] = _words.joined(tags)
        item["noRestrictions"] = staff.get("allergens") == [] and not tags
        item["note"] = _text(staff.get("note"))
        return item

    def swaps(self, swaps: dict) -> list[tuple[list[int], str, str]]:
        """(seats, requirement id, text) of every swap a seat needs, ordered
        by the lowest seat."""
        found = [
            (self.seats_of[requirement_id], requirement_id, text)
            for requirement_id, text in swaps.items()
            if self.seats_of.get(requirement_id)
        ]
        return sorted(found, key=lambda swap: swap[0][0])

    def seating(self, widget: dict, base: dict) -> dict:
        menu = self.menu
        tree = _seating(base)
        table = menu.get("table")
        if table is not None and widget.get("showScheme", True):
            letters = {
                number: [self.requirements[requirement_id]["letter"] for requirement_id in occupant["requirements"]]
                for number, occupant in sorted(self.occupants.items())
                if occupant["requirements"]
            }
            tree["scheme"] = _table.staff_scheme(table, letters=letters, **_couple(menu.get("couple") or {}))
        if widget.get("showLegend", True):
            tree["legend"] = [
                {"letter": requirement["letter"], "label": requirement["label"]}
                for requirement_id, requirement in self.requirements.items()
                if requirement_id in self.seats_of
            ]
        if widget.get("showTable", True):
            numbers = range(1, len(_table.expand_seats(table)) + 1) if table is not None else sorted(self.occupants)
            tree["rows"] = [self.row(number) for number in numbers]
        tree["footnote"] = _text((widget.get("staff") or {}).get("footnote"))
        return tree

    def row(self, number: int) -> dict:
        occupant = self.occupants.get(number)
        if occupant is None:  # a free or a reserved seat
            return {
                "number": number,
                "name": "",
                "isPlusOne": False,
                "hostName": "",
                "roleLabel": "",
                "isCouple": False,
                "isFree": True,
                "tags": [],
            }
        return {
            "number": number,
            "name": occupant["name"],
            "isPlusOne": occupant["isPlusOne"],
            "hostName": occupant["hostName"],
            "roleLabel": occupant["roleLabel"],
            "isCouple": occupant["isCouple"],
            "isFree": False,
            "tags": [
                _text(self.requirements[requirement_id].get("tag")) or self.requirements[requirement_id]["label"]
                for requirement_id in occupant["requirements"]
            ],
        }


# --------------------------------------------------------------------------
# All pages
# --------------------------------------------------------------------------


def build_trees(menu: dict, guests: list, report: Any, settings: Settings = DEFAULT_SETTINGS) -> Trees:
    """The trees of every page of checked data.

    A guest page whose table plan cannot be laid out (`_table.TableError`,
    which names seat numbers at most; checked data never raises it) is an
    error of its record and has no tree.  The staff tree is built even
    without a staff record, for `Trees.usage`, but returned only with one.
    """
    usage = Usage()
    public = public_menu(menu)
    pages: list[Page] = []
    staff_number = 0
    for number, record in enumerate(guests, start=1):
        if record.get("staff") is True:
            staff_number = staff_number or number
            continue
        try:
            tree = _GuestPage(public, own_record(record), settings, usage).tree()
        except _table.TableError as exc:
            for message in exc.errors:
                report.error(f"{guest_where(number)}: {message}")
            continue
        pages.append(Page(number, record["token"], tree))
    staff_page = None
    try:
        tree = _StaffPage(menu, guests, settings, usage).tree()
    except _table.TableError as exc:
        where = guest_where(staff_number) if staff_number else MENU_FILE
        for message in exc.errors:
            report.error(f"{where}: {message}")
    else:
        if staff_number:
            staff_page = Page(staff_number, guests[staff_number - 1]["token"], tree)
    return Trees(pages, staff_page, usage)


__all__ = [
    "Settings",
    "DEFAULT_SETTINGS",
    "Page",
    "Usage",
    "Trees",
    "public_menu",
    "own_record",
    "build_trees",
]
