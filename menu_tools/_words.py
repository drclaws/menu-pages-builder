"""The words of the pages: the English defaults, a menu's own words and the
plural rules.

A menu chooses its language with the `menu.json` field "lang" (a language
tag, "en" when the field is left out) and may give its own words in
"strings": any of the words below for an English menu, every one of them for
a menu in another language (`menu_tools._schema` checks them).  `Words`
holds the result: the menu's words over the English table (`ENGLISH`).

The page fragments read the fixed texts (`MARKUP_KEYS`) from the root of the
page tree.  The functions here join the other words with seat numbers, names
and counts before they reach a fragment: "Seats 8 & 9", "Olga — blue, your
guest — dark red", "If chosen by seat 3 (no nuts) — ...", "14 guests".

A pattern holds placeholders in braces ("updated {date}"), filled in one
pass: a value that holds braces stays as it is.  A plural word gives a form
per plural category ("one", "few", "other"...), each with the placeholder
{n}; the rule that picks the category comes from the language (whole numbers
only, after the plural rules of Unicode CLDR).

The typographic marks are not words: ", " between the items of a list,
" — " between seats and what to do for them, " · " between the parts of a
line, and the full stop after a swap line that ends without one.

Seat numbers are always listed in ascending order.  Standard library only.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping, NamedTuple, Sequence

#: The language of a menu without the field "lang".
DEFAULT_LANG = "en"
#: The language of the built-in words.
ENGLISH_LANGUAGE = "en"

#: Every word of the pages and its English default, in the order of the
#: pages: the frame, the table plan, the seat table, the sets, the words
#: joined with seat numbers, the default section titles, the counters.
ENGLISH: dict[str, Any] = {
    "pageTitle": "Dinner menu",
    "staffVersion": "Staff version · not for guests",
    "updated": "updated {date}",
    "contact": "Contact on the night: {contact}",
    "sections": "Sections",
    "tablePlan": "Table plan: {table}, {seats}. {yours}: {colours}",
    "seatCount": {"one": "{n} seat", "other": "{n} seats"},
    "you": "You",
    "seatNumber": "No.",
    "guestAndNotes": "Guest · dietary notes",
    "guestOf": "{name}’s guest",
    "nameBlank": "[name]",
    "noRestrictions": "no restrictions",
    "pairedWith": "Paired with {pairing}",
    "seat": "Seat",
    "seats": "Seats",
    "seatInline": "seat",
    "seatsInline": "seats",
    "and": "&",
    "yourGuest": "your guest",
    "seatColours": ("blue", "dark red", "green"),
    "swapFirst": "If chosen by",
    "swapNext": "By",
    "yourSeat": "Your seat",
    "yourSeats": "Your seats",
    "staffSeating": "Seating and dietary notes",
    "guestCount": {"one": "{n} guest", "other": "{n} guests"},
    "noteCount": {"one": "{n} dietary note", "other": "{n} dietary notes"},
}

#: The patterns and their placeholders, every one of them required.
PATTERNS: dict[str, tuple[str, ...]] = {
    "updated": ("date",),
    "contact": ("contact",),
    "tablePlan": ("table", "seats", "yours", "colours"),
    "guestOf": ("name",),
    "pairedWith": ("pairing",),
}
#: The plural words; each of their forms holds the placeholder {n}.
PLURALS = ("seatCount", "guestCount", "noteCount")
COUNT_PLACEHOLDER = "n"
#: The word that is a list of names: one per seat colour of the table plan
#: (`_table.SEAT_COLOURS`).
COLOUR_NAMES = "seatColours"
#: The fixed texts the template and the fragments read from the page root.
MARKUP_KEYS = (
    "pageTitle",
    "staffVersion",
    "sections",
    "you",
    "seatNumber",
    "guestAndNotes",
    "nameBlank",
    "noRestrictions",
)

#: Between list items, and around the word "and" before the last item.
LIST_SEPARATOR = ", "
#: Between seats and what to do for them, and between a name and its colour.
DASH = " — "
#: Between the parts of a line ("vegan · gluten-free").
DOT = " · "

#: A line that ends with one of these gets no full stop of its own.
_FINAL_MARKS = (".", "!", "?")

#: A placeholder: a name in braces.
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]{0,63})\}")


# --------------------------------------------------------------------------
# Plural rules
# --------------------------------------------------------------------------

#: The plural categories, in the order the CLDR rules list them.
CATEGORIES = ("zero", "one", "two", "few", "many", "other")


class PluralRule(NamedTuple):
    """The categories a language uses for whole numbers and the function
    that picks one for a number."""

    forms: tuple[str, ...]
    select: Callable[[int], str]


def _one(n: int) -> str:
    return "one" if n == 1 else "other"


def _zero_or_one(n: int) -> str:
    return "one" if n in (0, 1) else "other"


def _few(n: int) -> bool:
    """2-4 in the last digit, except 12-14."""
    return 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14


def _east_slavic(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    return "few" if _few(n) else "many"


def _bosnian_croatian_serbian(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    return "few" if _few(n) else "other"


def _polish(n: int) -> str:
    if n == 1:
        return "one"
    return "few" if _few(n) else "many"


def _czech_slovak(n: int) -> str:
    if n == 1:
        return "one"
    return "few" if 2 <= n <= 4 else "other"


def _slovenian(n: int) -> str:
    return {1: "one", 2: "two", 3: "few", 4: "few"}.get(n % 100, "other")


def _other(_n: int) -> str:
    return "other"


#: "one" for 1, "other" for every other number; also the rule of a language
#: without a built-in one.
ONE_OTHER = PluralRule(("one", "other"), _one)

_RULES: dict[str, PluralRule] = {}
for _languages, _rule in (
    (
        ("af", "az", "bg", "ca", "da", "de", "el", "en", "eo", "es", "et", "eu", "fi", "fo", "fy", "gl",
         "hu", "it", "ka", "kk", "ky", "lb", "mn", "nb", "nl", "nn", "no", "rm", "sq", "sv", "sw", "tr",
         "uz"),
        ONE_OTHER,
    ),
    (("fr", "pt"), PluralRule(("one", "other"), _zero_or_one)),
    (("ru", "uk", "be"), PluralRule(("one", "few", "many"), _east_slavic)),
    (("bs", "hr", "sr"), PluralRule(("one", "few", "other"), _bosnian_croatian_serbian)),
    (("pl",), PluralRule(("one", "few", "many"), _polish)),
    (("cs", "sk"), PluralRule(("one", "few", "other"), _czech_slovak)),
    (("sl",), PluralRule(("one", "two", "few", "other"), _slovenian)),
    (("ja", "zh", "ko", "vi", "th", "id", "ms"), PluralRule(("other",), _other)),
):
    for _language in _languages:
        _RULES[_language] = _rule
del _languages, _rule, _language


def language(tag: str) -> str:
    """The primary subtag of a language tag, in lower case: "sr-Latn" -> "sr"."""
    return tag.split("-", 1)[0].lower()


def plural_rule(tag: str) -> PluralRule | None:
    """The plural rule of the tag's language; None when there is no built-in one."""
    return _RULES.get(language(tag))


# --------------------------------------------------------------------------
# The words of a menu
# --------------------------------------------------------------------------


def placeholders(text: str) -> list[str]:
    """The names of the placeholders of a text, in order."""
    return _PLACEHOLDER_RE.findall(text)


def fill(pattern: str, values: Mapping[str, str]) -> str:
    """The pattern with each placeholder of `values` replaced, in one pass."""
    return _PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), pattern)


class Words:
    """The words of one menu: its language tag, its plural rule, and every
    word, the menu's own over the English defaults.  Checked data gives
    every word for a language other than English."""

    def __init__(self, lang: str = DEFAULT_LANG, strings: Mapping[str, Any] | None = None):
        self.lang = lang
        self.rule = plural_rule(lang) or ONE_OTHER
        self.table = {**ENGLISH, **(strings or {})}

    @classmethod
    def of(cls, source: Mapping[str, Any]) -> "Words":
        """The words of a menu, or of the part of it a guest page is built from."""
        return cls(source.get("lang", DEFAULT_LANG), source.get("strings"))

    def __getitem__(self, key: str) -> Any:
        return self.table[key]

    def fill(self, key: str, **values: str) -> str:
        return fill(self.table[key], values)

    def count(self, key: str, n: int) -> str:
        """The plural form of the word for the number: "1 guest", "14 guests"."""
        forms = self.table[key]
        return fill(forms[self.rule.select(n)], {COUNT_PLACEHOLDER: str(n)})

    def markup(self) -> dict[str, str]:
        """The fixed texts the template and the fragments read."""
        return {key: self.table[key] for key in MARKUP_KEYS}


#: The English words.
ENGLISH_WORDS = Words()


# --------------------------------------------------------------------------
# Words with numbers and names
# --------------------------------------------------------------------------


def _series(words: Words, texts: Sequence[str]) -> str:
    """The texts in their order, the word "and" before the last one and
    LIST_SEPARATOR between the others."""
    if len(texts) < 2:
        return "".join(texts)
    return LIST_SEPARATOR.join(texts[:-1]) + f" {words['and']} " + texts[-1]


def number_list(words: Words, numbers: Iterable[int]) -> str:
    """`[9, 8]` -> "8 & 9"; `[10, 8, 9]` -> "8, 9 & 10"; `[8]` -> "8"."""
    return _series(words, [str(number) for number in sorted(numbers)])


def seat_label(words: Words, numbers: Sequence[int]) -> str:
    """"Seat 8", "Seats 8 & 9", "Seats 8, 9 & 10": one seat or several, not
    a plural form (the numbers are a list, not a quantity)."""
    word = words["seat"] if len(numbers) == 1 else words["seats"]
    return f"{word} {number_list(words, numbers)}"


def seats_inline(words: Words, numbers: Sequence[int]) -> str:
    """"seat 3", "seats 10 & 14": the seats inside a sentence."""
    word = words["seatInline"] if len(numbers) == 1 else words["seatsInline"]
    return f"{word} {number_list(words, numbers)}"


def seat_names(words: Words, name: str, seats: Sequence[str]) -> list[str]:
    """Who sits at each of a record's seats, in seat order: the seat's name;
    without one, the record's name at the first seat and "your guest" at a
    +1.  `seats` holds each seat's name, "" for a seat without one.
    `["", "Oscar"]` for "Olga" -> ["Olga", "Oscar"]; `["", ""]` ->
    ["Olga", "your guest"].  Only the record's own page shows these names."""
    return [seat or (name if position == 0 else words["yourGuest"]) for position, seat in enumerate(seats)]


def colour_key(words: Words, names: Sequence[str]) -> str:
    """Whose seat is marked in which colour, for the table plan's text: each
    name with the colour of its place in the record, "Olga — blue",
    "Olga — blue, your guest — dark red".  A record has at most as many
    seats as there are colours."""
    colours = words["seatColours"]
    return LIST_SEPARATOR.join(f"{name}{DASH}{colours[position]}" for position, name in enumerate(names))


def section_title(words: Words, seats: int) -> str:
    """The default title of a guest's seating section, by the number of seats."""
    return words["yourSeat"] if seats == 1 else words["yourSeats"]


def plan_text(words: Words, table: str, total: int, names: Sequence[str]) -> str:
    """The text of a guest's table plan: "Table plan: L-shaped table, 16
    seats. Your seat: Olga — blue"; `names` are who sits at the record's
    seats (`seat_names`)."""
    return words.fill(
        "tablePlan",
        table=table,
        seats=words.count("seatCount", total),
        yours=section_title(words, len(names)),
        colours=colour_key(words, names),
    )


def counted(words: Words, key: str, count: int) -> str:
    """The plural word `key` for the number: "1 guest", "14 guests"."""
    return words.count(key, count)


def guests_text(words: Words, count: int) -> str:
    """The number of taken seats on the staff page: "14 guests"."""
    return counted(words, "guestCount", count)


def notes_text(words: Words, count: int) -> str:
    """The number of seats with a dietary note: "5 dietary notes"; empty for none."""
    return counted(words, "noteCount", count) if count else ""


def updated_text(words: Words, date: str) -> str:
    """"updated 12 June 2030"; empty without a date."""
    return words.fill("updated", date=date) if date else ""


def contact_text(words: Words, contact: str) -> str:
    """"Contact on the night: Selma"; empty without a contact."""
    return words.fill("contact", contact=contact) if contact else ""


def host_line(words: Words, host: str) -> str:
    """Whose guest a +1 is: "Olga’s guest"; empty without a host."""
    return words.fill("guestOf", name=host) if host else ""


def pairing_text(words: Words, pairing: str) -> str:
    """"Paired with white wine"; empty without a pairing."""
    return words.fill("pairedWith", pairing=pairing) if pairing else ""


def joined(parts: Iterable[str]) -> str:
    """The non-empty parts joined by DOT: "with the starters · 6 bottles"."""
    return DOT.join(part for part in parts if part)


def dish_swap_line(words: Words, numbers: Sequence[int], text: str) -> str:
    """"Seat 3 — serve the nut-free version", "Seats 10 & 14 — ..."."""
    return f"{seat_label(words, numbers)}{DASH}{text}"


def set_swap_line(words: Words, numbers: Sequence[int], label: str, text: str, *, first: bool) -> str:
    """"If chosen by seat 3 (no nuts) — serve it without the crust." for the
    first swap of a set, "By seats 10 & 14 (no lactose) — ..." for the next."""
    lead = words["swapFirst"] if first else words["swapNext"]
    stop = "" if text.endswith(_FINAL_MARKS) else "."
    return f"{lead} {seats_inline(words, numbers)} ({label}){DASH}{text}{stop}"


def drink_reminder(words: Words, numbers: Sequence[int], text: str) -> str:
    """"seat 1 — no alcohol": the end of a drink's line."""
    return f"{seats_inline(words, numbers)}{DASH}{text}"


__all__ = [
    "DEFAULT_LANG",
    "ENGLISH_LANGUAGE",
    "ENGLISH",
    "ENGLISH_WORDS",
    "PATTERNS",
    "PLURALS",
    "COUNT_PLACEHOLDER",
    "COLOUR_NAMES",
    "MARKUP_KEYS",
    "CATEGORIES",
    "PluralRule",
    "ONE_OTHER",
    "language",
    "plural_rule",
    "placeholders",
    "fill",
    "Words",
    "number_list",
    "seat_label",
    "seats_inline",
    "seat_names",
    "colour_key",
    "section_title",
    "plan_text",
    "counted",
    "guests_text",
    "notes_text",
    "updated_text",
    "contact_text",
    "host_line",
    "pairing_text",
    "joined",
    "dish_swap_line",
    "set_swap_line",
    "drink_reminder",
]
