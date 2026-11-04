"""The words the build joins with seat numbers, names and counts.

The page fragments hold every fixed interface text ("Staff version", "No.",
"Paired with", "You", "+1", "[name]" and so on).  The texts here are the
ones the build combines with numbers or names before they reach a
fragment: "Seats 8 & 9", "Olga — blue, your guest — dark red", "If chosen
by seat 3 (no nuts) - ...", "14 guests".  Keeping them in one place makes
the menu's wording easy to change.

Seat numbers are always listed in ascending order.  Standard library only.
"""

from __future__ import annotations

from typing import Iterable, Sequence

SEAT = "Seat"
SEATS = "Seats"
#: The same inside a sentence.
SEAT_INLINE = "seat"
SEATS_INLINE = "seats"

#: Between list items, and before the last item.
LIST_SEPARATOR = ", "
LAST_SEPARATOR = " & "
#: Between seats and what to do for them, and between a name and its colour.
DASH = " — "
#: Between the parts of a line ("vegan · gluten-free").
DOT = " · "

#: In place of an unknown companion's name.
YOUR_GUEST = "your guest"

#: The colour names of a guest record's seats, in seat order
#: (`_table.SEAT_COLOURS`, the tokens `--color-seat-<n>`): the table plan
#: says in words whose seat is marked in which colour.
SEAT_COLOUR_NAMES = ("blue", "dark red", "green")

#: The first and the next swap lines of a set.
IF_CHOSEN_BY = "If chosen by"
BY = "By"

#: The default titles of the section with the seating widget.
YOUR_SEAT = "Your seat"
YOUR_SEATS = "Your seats"
STAFF_SEATING = "Seating and dietary notes"

#: The counters of the staff page.
GUEST = "guest"
GUESTS = "guests"
NOTE = "dietary note"
NOTES = "dietary notes"

#: A line that ends with one of these gets no full stop of its own.
_FINAL_MARKS = (".", "!", "?")


def _series(texts: Sequence[str], last: str) -> str:
    """The texts in their order, `last` before the last one and
    LIST_SEPARATOR between the others."""
    if len(texts) < 2:
        return "".join(texts)
    return LIST_SEPARATOR.join(texts[:-1]) + last + texts[-1]


def number_list(numbers: Iterable[int]) -> str:
    """`[9, 8]` -> "8 & 9"; `[10, 8, 9]` -> "8, 9 & 10"; `[8]` -> "8"."""
    return _series([str(number) for number in sorted(numbers)], LAST_SEPARATOR)


def seat_label(numbers: Sequence[int]) -> str:
    """"Seat 8", "Seats 8 & 9", "Seats 8, 9 & 10"."""
    word = SEAT if len(numbers) == 1 else SEATS
    return f"{word} {number_list(numbers)}"


def seats_inline(numbers: Sequence[int]) -> str:
    """"seat 3", "seats 10 & 14": the seats inside a sentence."""
    word = SEAT_INLINE if len(numbers) == 1 else SEATS_INLINE
    return f"{word} {number_list(numbers)}"


def seat_names(name: str, seats: Sequence[str]) -> list[str]:
    """Who sits at each of a record's seats, in seat order: the seat's name;
    without one, the record's name at the first seat and "your guest" at a
    +1.  `seats` holds each seat's name, "" for a seat without one.
    `["", "Oscar"]` for "Olga" -> ["Olga", "Oscar"]; `["", ""]` ->
    ["Olga", "your guest"].  Only the record's own page shows these names."""
    return [seat or (name if position == 0 else YOUR_GUEST) for position, seat in enumerate(seats)]


def colour_key(names: Sequence[str]) -> str:
    """Whose seat is marked in which colour, for the table plan's text: each
    name with the colour of its place in the record, "Olga — blue",
    "Olga — blue, your guest — dark red".  A record has at most as many
    seats as there are colours."""
    return LIST_SEPARATOR.join(
        f"{name}{DASH}{SEAT_COLOUR_NAMES[position]}" for position, name in enumerate(names)
    )


def section_title(seats: int) -> str:
    """The default title of a guest's seating section, by the number of seats."""
    return YOUR_SEAT if seats == 1 else YOUR_SEATS


def counted(count: int, one: str, many: str) -> str:
    """"1 guest", "14 guests"."""
    return f"{count} {one if count == 1 else many}"


def guests_text(count: int) -> str:
    """The number of taken seats on the staff page: "14 guests"."""
    return counted(count, GUEST, GUESTS)


def notes_text(count: int) -> str:
    """The number of seats with a dietary note: "5 dietary notes"; empty for none."""
    return counted(count, NOTE, NOTES) if count else ""


def joined(parts: Iterable[str]) -> str:
    """The non-empty parts joined by DOT: "with the starters · 6 bottles"."""
    return DOT.join(part for part in parts if part)


def listed(parts: Iterable[str]) -> str:
    """The parts as one line: "Water, lemonade, juice"."""
    return LIST_SEPARATOR.join(parts)


def dish_swap_line(numbers: Sequence[int], text: str) -> str:
    """"Seat 3 — serve the nut-free version", "Seats 10 & 14 — ..."."""
    return f"{seat_label(numbers)}{DASH}{text}"


def set_swap_line(numbers: Sequence[int], label: str, text: str, *, first: bool) -> str:
    """"If chosen by seat 3 (no nuts) — serve it without the crust." for the
    first swap of a set, "By seats 10 & 14 (no lactose) — ..." for the next."""
    lead = IF_CHOSEN_BY if first else BY
    stop = "" if text.endswith(_FINAL_MARKS) else "."
    return f"{lead} {seats_inline(numbers)} ({label}){DASH}{text}{stop}"


def drink_reminder(numbers: Sequence[int], text: str) -> str:
    """"seat 1 — no alcohol": the end of a drink's line."""
    return f"{seats_inline(numbers)}{DASH}{text}"


__all__ = [
    "number_list",
    "seat_label",
    "seats_inline",
    "seat_names",
    "colour_key",
    "section_title",
    "counted",
    "guests_text",
    "notes_text",
    "joined",
    "listed",
    "dish_swap_line",
    "set_swap_line",
    "drink_reminder",
]
