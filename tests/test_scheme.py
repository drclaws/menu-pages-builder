"""The table plan on a page: the scheme partial on the geometry's objects.

The partial `fragments/partials/scheme.html` draws an inline SVG from the
`scheme` object of `menu_tools._table` with the build's template engine:
every number comes from the object, the markup only places it.
The objects here are built by the geometry for four table shapes - the
L-shaped tables of the data sets with 16 and 19 seats, a straight table with
the couple facing each other and a U-shaped one with the couple label upright
on a vertical arm - and rendered in the frame the seating widget gives the
partial.  The output goes through the finished HTML page and SVG file checks
(`check_html`, `check_svg`).

The names in the drawing (the couple label on the staff plan, the names of
the guest's seats in the guest plan's text) come from the data set and the
English words of `menu_tools._words`, never from literals here.

The radii the geometry writes depend on the border widths the style sheet
draws: the last tests tie those `menu_tools._table` constants to the
`assets/app.css` tokens.
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys
import unittest
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core as core  # noqa: E402  (imported after sys.path is prepared)
from menu_tools import _table, _words  # noqa: E402
from tests import fixtures  # noqa: E402
from tests.test_table import straight_table, u_table, wide_l_table  # noqa: E402

#: Plain properties of `:root` read like tokens: the theme is part of the design.
ROOT_PROPERTIES = frozenset({"color-scheme"})

COMMENT_RE = re.compile(r"/\*.*?(?:\*/|\Z)", re.DOTALL)
ROOT_RE = re.compile(r"(?<![\w-]):root\s*\{")
AT_RULE_RE = re.compile(r"@(media|supports)\b([^{;]*)\{")


def split_declarations(body):
    """Split a rule body at the `;` outside brackets and strings."""
    parts = []
    depth = 0
    quote = ""
    start = 0
    for index, char in enumerate(body):
        if quote:
            if char == quote and body[index - 1] != "\\":
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    return parts


def block_end(text, start):
    """The index just past the `}` closing the block whose body starts at `start`."""
    depth = 1
    end = start
    while end < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[end], 0)
        end += 1
    return end


def token_contexts(css, context=""):
    """{context: {token: value}} of the `:root` rules of a style sheet.

    Tokens are the custom properties and the properties of `ROOT_PROPERTIES`.
    The context is "" at the top level, otherwise the at-rule preludes with
    their whitespace collapsed ("@media (min-width: 48em)"); nested blocks
    join their preludes. Values have their whitespace collapsed; when a token
    is declared twice in one context the last one wins. Contexts without
    tokens are left out.
    """
    text = COMMENT_RE.sub(" ", css)
    contexts = {}
    depth = 0
    position = 0
    while position < len(text):
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == ":" and depth == 0 and ROOT_RE.match(text, position):
            start = ROOT_RE.match(text, position).end()
            end = block_end(text, start)
            for declaration in split_declarations(text[start:end - 1]):
                name, colon, value = declaration.partition(":")
                name = name.strip()
                if colon and (name.startswith("--") or name in ROOT_PROPERTIES):
                    contexts.setdefault(context, {})[name] = " ".join(value.split())
            position = end
            continue
        elif char == "@" and depth == 0 and AT_RULE_RE.match(text, position):
            match = AT_RULE_RE.match(text, position)
            end = block_end(text, match.end())
            prelude = " ".join(("@%s %s" % (match.group(1), match.group(2))).split())
            inner = " ".join((context + " " + prelude).split())
            for key, tokens in token_contexts(text[match.end():end - 1], inner).items():
                contexts.setdefault(key, {}).update(tokens)
            position = end
            continue
        position += 1
    return contexts


FRAGMENTS_DIR = ROOT / "fragments"
APP_CSS = ROOT / "assets" / "app.css"
#: The seating widget's frame around the partial.
FRAME = "<!-- with:scheme --><!-- include:partials/scheme --><!-- endwith -->"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

#: shape -> (table, couple seats (of the staff plan), guest seats (in record
#: order), staff letters by seat number).
SHAPES = {
    "l16": (fixtures.l_table_16, [4, 5], [8, 9],
            {1: ["A"], 3: ["N"], 7: ["V"], 10: ["G", "L"], 14: ["L"]}),
    "l19": (fixtures.l_table_19, [6, 7], [19, 1],
            {3: ["V"], 4: ["N"], 7: ["G"], 10: ["G", "L"], 11: ["A"], 14: ["L"], 18: ["V"]}),
    "straight12": (straight_table, [4, 10], [7, 8], {2: ["N"], 7: ["G", "V"], 12: ["A"]}),
    # the couple sits on the outer side of the west arm: its label stands upright
    "u20": (u_table, [18, 19], [11, 12], {1: ["N"], 8: ["G", "L"], 20: ["A", "N"]}),
}

#: The attributes each drawing element may have: geometry, classes and the
#: drawing's accessibility, nothing else.
ATTRIBUTES = {
    "svg": {"class", "viewbox", "width", "height", "focusable", "role", "aria-label",
            "aria-hidden"},
    "path": {"class", "d"},
    "g": {"class"},
    "circle": {"class", "cx", "cy", "r"},
    "text": {"class", "x", "y", "transform"},
}
#: Every class of the drawing; the modifiers come from the enumerations.
CLASSES = frozenset({
    "scheme", "scheme__table", "scheme__couple", "seat", "seat__ring", "seat__circle",
    "seat__number", "seat-badge", "seat-badge__circle", "seat-badge__letter", "seat-label",
    *(f"seat--{kind}" for kind in _table.KINDS), *(f"seat--{mark}" for mark in _table.MARKS),
    *(f"seat--colour-{colour}" for colour in _table.SEAT_COLOURS),
    *(f"seat-label--{anchor}" for anchor in _table.ANCHORS),
})
NUMBER = r"-?\d+(?:\.(?:5|25|75))?"
NUMBER_ATTRIBUTES = ("width", "height", "cx", "cy", "r", "x", "y")

#: The English words of the pages.
EN = _words.ENGLISH_WORDS
#: Who sits at the guest record's seats, in order.
NAMES = ("Olga", EN["yourGuest"], "Hugo")

#: sha256 of the 16-seat L-shaped table's markup: for a guest with two seats,
#: a guest with one seat and the staff; changing the partial changes it.
DIGEST = "fb0b611df9099725a326612f515935b766aa07ad4cd1e64785970944b7f508d4"


def couple(shape: str) -> dict:
    return {"couple_seats": SHAPES[shape][1], "couple_label": fixtures.COUPLE_LABEL,
            "couple_arm": None}


def guest_object(shape: str, own: list | None = None, table: dict | None = None) -> dict:
    """The guest's object; the seats of `own` are named after `NAMES`."""
    make, _couple, seats, _letters = SHAPES[shape]
    own = seats if own is None else own
    table = table or make()
    text = _words.plan_text(EN, table["label"], len(_table.expand_seats(table)), NAMES[:len(own)])
    return _table.guest_scheme(table, own_seats=own, plan_text=text)


def staff_object(shape: str, table: dict | None = None) -> dict:
    make, _couple, _seats, letters = SHAPES[shape]
    return _table.staff_scheme(table or make(), letters=letters, **couple(shape))


_TEMPLATE = core.parse_template(FRAME, "frame", core.load_fragments(FRAGMENTS_DIR))


def render(scheme: dict, staff_page: bool) -> str:
    """The partial for the audience's page, as the build publishes it."""
    output = _TEMPLATE.render({"isStaff": staff_page, "strings": EN.markup(), "scheme": scheme})
    return core.strip_html_comments(output, "frame")


def html_page(svg: str) -> str:
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            "<title>Plan</title>\n</head>\n<body>\n" + svg + "</body>\n</html>\n")


def svg_file(svg: str) -> str:
    return svg.replace("<svg ", f'<svg xmlns="{SVG_NAMESPACE}" ', 1)


class Elements(HTMLParser):
    """(tag, attributes, text) of every element of the markup, in order."""

    def __init__(self, markup: str):
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, dict, str]] = []
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, {name: value or "" for name, value in attrs}, ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.found and data.strip():
            tag, attributes, text = self.found[-1]
            self.found[-1] = (tag, attributes, text + data)

    def of_class(self, name: str) -> list[tuple[str, dict, str]]:
        return [item for item in self.found if name in item[1].get("class", "").split()]


def every_drawing():
    """(shape, audience, object, markup) for every shape: a guest with two
    seats, a guest with one seat, the staff."""
    for shape in SHAPES:
        own = SHAPES[shape][2]
        for audience, scheme in (("guest", guest_object(shape)), ("guest-alone", guest_object(shape, own[:1])),
                                 ("staff", staff_object(shape))):
            yield shape, audience, scheme, render(scheme, audience == "staff")


# --------------------------------------------------------------------------
# The markup
# --------------------------------------------------------------------------


class MarkupTest(unittest.TestCase):
    def test_every_shape_passes_the_checks_of_a_page_and_of_an_svg(self):
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                self.assertTrue(svg.startswith('\n<svg class="scheme" viewBox="0 0 318 310" '
                                               'width="318" height="310" focusable="false"'))
                self.assertEqual(core.check_html(html_page(svg), lambda _path: False), [])
                self.assertEqual(core.check_svg(svg_file(svg)), [])
                core.check_rendered(html_page(svg))

    def test_a_field_of_another_size_sizes_the_drawing(self):
        table = wide_l_table()
        for audience, scheme in (("guest", _table.guest_scheme(table, own_seats=[8], plan_text="x")),
                                 ("staff", _table.staff_scheme(table, couple_seats=[], couple_label=None,
                                                               couple_arm=None, letters={15: ["A"]}))):
            with self.subTest(audience=audience):
                svg = render(scheme, audience == "staff")
                self.assertTrue(svg.startswith('\n<svg class="scheme" viewBox="0 0 360 310" '
                                               'width="360" height="310" focusable="false"'))
                self.assertEqual(core.check_html(html_page(svg), lambda _path: False), [])
                self.assertEqual(core.check_svg(svg_file(svg)), [])

    def test_attributes_hold_geometry_classes_and_accessibility_only(self):
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                for tag, attributes, _text in Elements(svg).found:
                    self.assertIn(tag, ATTRIBUTES)
                    self.assertLessEqual(set(attributes), ATTRIBUTES[tag], tag)
                    self.assertLessEqual(set(attributes["class"].split()), CLASSES)
                for pattern in (r"\sstyle\s*=", r"(?i)<style", r"(?i)<script", r"\shref\s*=",
                                r"(?i)<foreignobject", r"(?i)<title", r"\sid\s*=", r"\sfill\s*=",
                                r"\sstroke", r"\sfont", r"\{\{", r"\}\}"):
                    self.assertNotRegex(svg, pattern)

    def test_numbers_are_whole_half_or_quarter_units(self):
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                for tag, attributes, _text in Elements(svg).found:
                    for name in NUMBER_ATTRIBUTES:
                        if name in attributes:
                            self.assertRegex(attributes[name], rf"\A{NUMBER}\Z", (tag, name))
                    if "d" in attributes:
                        for token in re.findall(r"[^MLAZ ]+", attributes["d"]):
                            self.assertRegex(token, rf"\A{NUMBER}\Z")
                    if "transform" in attributes:
                        self.assertEqual(attributes["transform"],
                                         f"rotate(-90 {attributes['x']} {attributes['y']})")
                self.assertRegex(svg, r'viewBox="0 0 318 310"')

    def test_the_layers_are_outline_couple_seats_badges_labels(self):
        layers = ("scheme__table", "scheme__couple", "seat", "seat-badge", "seat-label")
        expected = {"staff": ["scheme__table", "scheme__couple", "seat", "seat-badge"],
                    "guest": ["scheme__table", "seat"],
                    "guest-alone": ["scheme__table", "seat", "seat-label"]}
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                order = []
                for _tag, attributes, _text in Elements(svg).found:
                    first = attributes.get("class", "").split()[:1]
                    if first and first[0] in layers and (not order or order[-1] != first[0]):
                        order.append(first[0])
                self.assertEqual(order, expected[audience])

    def test_every_seat_once_at_its_centre_with_its_number_on_the_staff_plan_alone(self):
        for shape, audience, scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                elements = Elements(svg)
                numbers = [(attributes["x"], attributes["y"], text)
                           for _tag, attributes, text in elements.of_class("seat__number")]
                self.assertEqual(numbers, [(seat["cx"], seat["cy"], seat["number"])
                                           for seat in scheme["seats"]] if audience == "staff" else [])
                circles = [(attributes["cx"], attributes["cy"], attributes["r"])
                           for _tag, attributes, _text in elements.of_class("seat__circle")]
                self.assertEqual(circles, [(seat["cx"], seat["cy"], seat["r"])
                                           for seat in scheme["seats"]])
                groups = [attributes["class"]
                          for _tag, attributes, _text in elements.of_class("seat")]
                self.assertEqual(groups, [f"seat seat--{seat['kind']} seat--{seat['mark']}"
                                          + (f" seat--colour-{seat['colour']}" if seat["colour"] else "")
                                          for seat in scheme["seats"]])

    def test_the_couple_label_lies_flat_or_stands_upright_on_its_arm_of_the_staff_plan(self):
        cases = {"l16": False, "straight12": False, "u20": True}
        for shape, vertical in cases.items():
            scheme = staff_object(shape)
            label = scheme["couple"]
            with self.subTest(shape=shape):
                self.assertIs(label["vertical"], vertical)
                self.assertEqual(label["text"], fixtures.COUPLE_LABEL.upper())
                [(tag, attributes, text)] = Elements(render(scheme, True)).of_class("scheme__couple")
                self.assertEqual((attributes["x"], attributes["y"], text),
                                 (label["x"], label["y"], label["text"]))
                self.assertEqual(attributes.get("transform"),
                                 f"rotate(-90 {label['x']} {label['y']})" if vertical else None)
        # no couple label: no text in the arm
        scheme = _table.staff_scheme(fixtures.l_table_16(), letters={}, couple_seats=[4, 5],
                                     couple_label=None, couple_arm=None)
        self.assertNotIn("scheme__couple", render(scheme, True))

    def test_the_markup_keeps_one_line_per_layer_and_seat(self):
        cases = (
            # the svg tag, the outline, 16 seats, the end
            (render(guest_object("l16"), False), 1 + 1 + 16 + 1),
            # and the label "You"
            (render(guest_object("l16", [8]), False), 1 + 1 + 16 + 1 + 1),
            # the svg tag, the outline, the couple label, 16 seats, 6 badges, the end
            (render(staff_object("l16"), True), 1 + 1 + 1 + 16 + 6 + 1),
        )
        for svg, count in cases:
            lines = svg.strip("\n").split("\n")
            with self.subTest(count=count):
                self.assertEqual(len(lines), count)
                self.assertNotIn("", lines)
                self.assertNotRegex(svg, r">[ \t]+<")
                self.assertEqual(lines[-1], "</svg>")

    def test_the_digest_of_the_markup_is_fixed(self):
        text = (render(guest_object("l16"), False) + render(guest_object("l16", [8]), False)
                + render(staff_object("l16"), True))
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), DIGEST)


# --------------------------------------------------------------------------
# The guest and the staff
# --------------------------------------------------------------------------


def svg_tag(svg: str) -> dict:
    return Elements(svg).found[0][1]


class GuestTest(unittest.TestCase):
    def test_the_drawing_is_one_image_named_after_the_table_and_the_colours_of_the_seats(self):
        cases = (([8], "Table plan: L-shaped table, 16 seats. Your seat: Olga — blue"),
                 ([8, 9], "Table plan: L-shaped table, 16 seats. Your seats: Olga — blue, "
                          "your guest — dark red"),
                 ([9, 8, 10], "Table plan: L-shaped table, 16 seats. Your seats: Olga — blue, "
                              "your guest — dark red, Hugo — green"))
        for own, name in cases:
            with self.subTest(own=own):
                tag = svg_tag(render(guest_object("l16", own), False))
                self.assertEqual(tag["role"], "img")
                self.assertEqual(tag["aria-label"], name)
                self.assertEqual(tag["focusable"], "false")
                self.assertNotIn("aria-hidden", tag)
                # no seat number: the one number is the seat count
                self.assertEqual(re.findall(r"\d+", tag["aria-label"]), ["16"])

    def test_the_guest_sees_no_dietary_marks_no_couple_and_no_numbers(self):
        for shape in SHAPES:
            for own in (SHAPES[shape][2], SHAPES[shape][2][:1]):
                svg = render(guest_object(shape, own), False)
                with self.subTest(shape=shape, own=own):
                    for part in ("aria-hidden", "seat-badge", "seat--flagged", "seat--couple",
                                 "scheme__couple", "seat__number", fixtures.COUPLE_LABEL.upper()):
                        self.assertNotIn(part, svg)
                    self.assertEqual([text for _tag, _attributes, text in Elements(svg).found if text],
                                     ["You"] if len(own) == 1 else [])

    def test_rings_and_colours_on_the_own_seats_in_the_order_of_the_record(self):
        for shape in SHAPES:
            own = SHAPES[shape][2]
            scheme = guest_object(shape)
            elements = Elements(render(scheme, False))
            mine = [seat for seat in scheme["seats"] if seat["kind"] == "you"]
            with self.subTest(shape=shape):
                rings = [(attributes["cx"], attributes["cy"], attributes["r"])
                         for _tag, attributes, _text in elements.of_class("seat__ring")]
                self.assertEqual(rings, [(seat["cx"], seat["cy"], seat["ringR"]) for seat in mine])
                coloured = {attributes["class"].split()[-1]: seats["number"]
                            for (_tag, attributes, _text), seats
                            in zip(elements.of_class("seat"), scheme["seats"]) if seats["kind"] == "you"}
                self.assertEqual(coloured, {f"seat--colour-{colour}": str(number)
                                            for number, colour in zip(own, _table.SEAT_COLOURS)})
                self.assertEqual(elements.of_class("seat-label"), [])

    def test_the_one_seat_of_a_guest_gets_the_label_you(self):
        for shape in SHAPES:
            scheme = guest_object(shape, SHAPES[shape][2][:1])
            elements = Elements(render(scheme, False))
            with self.subTest(shape=shape):
                labels = [(attributes["class"], attributes["x"], attributes["y"], text)
                          for _tag, attributes, text in elements.of_class("seat-label")]
                self.assertEqual(labels, [
                    (f"seat-label seat-label--{label['anchor']}", label["x"], label["y"], "You")
                    for label in scheme["labels"]])
                self.assertEqual(len(labels), 1)
                self.assertEqual(len(elements.of_class("seat--colour-1")), 1)

    def test_three_own_seats_get_three_colours_and_no_label(self):
        scheme = guest_object("l16", [8, 9, 10])
        svg = render(scheme, False)
        self.assertEqual(svg.count('class="seat__ring"'), 3)
        for number, colour in zip((8, 9, 10), _table.SEAT_COLOURS):
            self.assertEqual(svg.count(f'<g class="seat seat--you seat--none seat--colour-{colour}">'), 1)
        self.assertNotIn("seat-label", svg)


class StaffTest(unittest.TestCase):
    def test_the_drawing_is_hidden_from_screen_readers(self):
        for shape in SHAPES:
            svg = render(staff_object(shape), True)
            tag = svg_tag(svg)
            with self.subTest(shape=shape):
                self.assertEqual(tag["aria-hidden"], "true")
                self.assertEqual(tag["focusable"], "false")
                self.assertNotIn("role", tag)
                self.assertNotIn("aria-label", tag)
                for part in ("seat--you", "seat__ring", "seat-label", "Your seat", "seat--colour"):
                    self.assertNotIn(part, svg)
                # the couple and the seat numbers
                self.assertEqual(svg.count("seat seat--couple "), len(SHAPES[shape][1]))
                self.assertEqual(len(Elements(svg).of_class("seat__number")), len(staff_object(shape)["seats"]))
                self.assertIn(fixtures.COUPLE_LABEL.upper(), svg)

    def test_a_badge_per_letter_and_a_flagged_seat_per_note(self):
        for shape in SHAPES:
            letters = SHAPES[shape][3]
            scheme = staff_object(shape)
            elements = Elements(render(scheme, True))
            with self.subTest(shape=shape):
                badges = [(attributes["x"], attributes["y"], text)
                          for _tag, attributes, text in elements.of_class("seat-badge__letter")]
                self.assertEqual([text for *_xy, text in badges],
                                 [letter for number in sorted(letters)
                                  for letter in letters[number]])
                self.assertEqual(badges, [(badge["cx"], badge["cy"], badge["letter"])
                                          for badge in scheme["badges"]])
                circles = [(attributes["cx"], attributes["cy"], attributes["r"])
                           for _tag, attributes, _text in elements.of_class("seat-badge__circle")]
                self.assertEqual(circles, [(badge["cx"], badge["cy"], badge["r"])
                                           for badge in scheme["badges"]])
                marked = [number for number, (_tag, attributes, _text)
                          in enumerate(elements.of_class("seat"), start=1)
                          if "seat--flagged" in attributes["class"].split()]
                self.assertEqual(marked, sorted(letters))


# --------------------------------------------------------------------------
# Values from the data and the audience branches
# --------------------------------------------------------------------------


class SafetyTest(unittest.TestCase):
    def test_the_table_label_the_names_and_the_couple_label_are_escaped(self):
        value = '<b>"x"&{{y}}'
        table = fixtures.l_table_16()
        table["label"] = value
        scheme = _table.guest_scheme(table, own_seats=[8], plan_text=_words.plan_text(EN, value, 16, [value]))
        svg = render(scheme, False)
        self.assertIn('aria-label="Table plan: &lt;b&gt;&quot;x&quot;&amp;&#123;&#123;y&#125;'
                      '&#125;, 16 seats. Your seat: &lt;b&gt;&quot;x&quot;&amp;&#123;&#123;y&#125;'
                      '&#125; — blue"', svg)
        staff_svg = render(_table.staff_scheme(table, letters={}, couple_seats=[4, 5], couple_label=value,
                                               couple_arm=None), True)
        self.assertIn(">&lt;B&gt;&quot;X&quot;&amp;&#123;&#123;Y&#125;&#125;</text>", staff_svg)
        for markup in (svg, staff_svg):
            self.assertNotIn("<b>", markup.lower())
            self.assertEqual(core.check_html(html_page(markup), lambda _path: False), [])
            self.assertEqual(core.check_svg(svg_file(markup)), [])

    def test_the_branches_of_the_audiences_guard_against_a_wrong_object(self):
        # a guest page never prints badges, the couple or the numbers, even
        # when the object has them
        guest = guest_object("l16")
        staff = staff_object("l16")
        guest.update(badges=copy.deepcopy(staff["badges"]), couple=copy.deepcopy(staff["couple"]))
        svg = render(guest, False)
        for part in ("seat-badge", "scheme__couple", "seat__number"):
            self.assertNotIn(part, svg)
        self.assertEqual(svg_tag(svg)["role"], "img")
        # the staff page never prints labels or colours nor names the guest's seats
        staff.update(labels=copy.deepcopy(guest_object("l16", [8])["labels"]),
                     planText="Table plan: L-shaped table, 16 seats. Your seat: Olga — blue", hidden=False)
        for seat in staff["seats"]:
            seat["colour"] = "1"
        svg = render(staff, True)
        for part in ("seat-label", "seat--colour", "Your seat", "Olga"):
            self.assertNotIn(part, svg)
        self.assertNotIn("role", svg_tag(svg))


# --------------------------------------------------------------------------
# The geometry's numbers and the style sheet's tokens
# --------------------------------------------------------------------------


def px(value: str) -> Fraction:
    """`1.5px` -> 3/2; anything else fails."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)px", value)
    if match is None:
        raise AssertionError(f"not a length in px: {value!r}")
    return Fraction(match.group(1))


def token_ties(css: str) -> list[str]:
    """Where the geometry's constants and the `css` tokens disagree.

    The build computes the seat radii from the border widths, so a seat's
    circle stays 30 (34) units across whatever the style sheet draws.  The
    field size is the markup's business alone (the style sheet takes it from
    the drawing's attributes).
    """
    tokens = token_contexts(css)[""]
    seat, flag = px(tokens["--line-width-seat"]), px(tokens["--line-width-flag"])
    half = Fraction(1, 2)
    expected = {
        "--line-width-seat": (seat, Fraction(_table.SEAT_STROKE)),
        "--line-width-flag": (flag, Fraction(_table.FLAG_STROKE)),
        "SEAT_R": (Fraction(_table.SEAT_R), _table.SEAT_DIAMETER * half - seat * half),
        "FLAG_R": (Fraction(_table.FLAG_R), _table.SEAT_DIAMETER * half - flag * half),
        "YOU_R": (Fraction(_table.YOU_R), _table.YOU_DIAMETER * half - seat * half),
        "RING_R": (Fraction(_table.RING_R), _table.YOU_DIAMETER * half + _table.RING_WIDTH),
    }
    return [f"{name}: {actual} against {wanted}"
            for name, (actual, wanted) in expected.items() if actual != wanted]


class TokenTieTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = APP_CSS.read_text(encoding="utf-8")

    def test_the_constants_of_the_geometry_follow_the_tokens(self):
        self.assertEqual(token_ties(self.css), [])

    def test_a_drift_on_either_side_is_caught(self):
        for old, new, name in (("--line-width-seat: 1.5px;", "--line-width-seat: 2px;", "SEAT_R"),
                               ("--line-width-flag: 2.5px;", "--line-width-flag: 3px;", "FLAG_R")):
            with self.subTest(token=old):
                self.assertEqual(self.css.count(old), 1)
                problems = token_ties(self.css.replace(old, new))
                self.assertTrue(problems)
                self.assertTrue(any(problem.startswith(name) for problem in problems), problems)
        for constant, value in (("SEAT_STROKE", "2"), ("YOU_R", "16"), ("RING_WIDTH", 5)):
            with self.subTest(constant=constant), mock.patch.object(_table, constant, value):
                self.assertTrue(token_ties(self.css))


# --------------------------------------------------------------------------
# The colours of a guest's seats
# --------------------------------------------------------------------------

#: Dichromacy at full severity, Machado, Oliveira and Fernandes (2009): a
#: matrix on linear sRGB.
DEFICIENCIES = {
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216),
                   (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413),
                     (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602),
                   (0.004733, 0.691367, 0.303900)),
}
#: The least lightness difference (CIE L*) between two seat colours.
LIGHTNESS_GAP = 12.5


def hex_colour(tokens: dict, name: str) -> str:
    """The #rrggbb value of a colour token, through var() references."""
    value = tokens[name]
    while value.startswith("var("):
        value = tokens[re.fullmatch(r"var\((--[\w-]+)\)", value).group(1)]
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        raise AssertionError(f"{name}: not a #rrggbb colour: {value}")
    return value


def linear_rgb(colour: str) -> tuple[float, float, float]:
    def channel(text: str) -> float:
        value = int(text, 16) / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return channel(colour[1:3]), channel(colour[3:5]), channel(colour[5:7])


def luminance(rgb: tuple[float, float, float]) -> float:
    """The WCAG 2 relative luminance."""
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast(first: str, second: str) -> float:
    light, dark = sorted((luminance(linear_rgb(first)), luminance(linear_rgb(second))), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def lightness(rgb: tuple[float, float, float]) -> float:
    """CIE L* of a linear sRGB colour (the grey it prints in)."""
    y = luminance(rgb)
    return 116 * y ** (1 / 3) - 16 if y > (6 / 29) ** 3 else y * (29 / 3) ** 3


def seen_with(rgb: tuple[float, float, float], deficiency: str) -> tuple[float, float, float]:
    matrix = DEFICIENCIES[deficiency]
    return tuple(min(1.0, max(0.0, sum(row[k] * rgb[k] for k in range(3)))) for row in matrix)


def seat_palette(css: str) -> list[str]:
    tokens = token_contexts(css)[""]
    return [hex_colour(tokens, f"--color-seat-{colour}") for colour in _table.SEAT_COLOURS]


class SeatColoursTest(unittest.TestCase):
    """The colour tokens of a guest's seats against the page rules: legible
    white text, visible on the card, apart in lightness (in grey and with a
    colour vision deficiency), not the dietary orange."""

    @classmethod
    def setUpClass(cls):
        cls.css = APP_CSS.read_text(encoding="utf-8")
        cls.tokens = token_contexts(cls.css)[""]
        cls.palette = seat_palette(cls.css)

    def test_a_token_and_a_name_per_colour_the_first_one_the_accent(self):
        names = sorted(name for name in self.tokens if name.startswith("--color-seat-"))
        self.assertEqual(names, [f"--color-seat-{colour}" for colour in _table.SEAT_COLOURS])
        self.assertEqual(len(EN["seatColours"]), len(_table.SEAT_COLOURS))
        self.assertEqual(len(set(EN["seatColours"])), len(EN["seatColours"]))
        self.assertEqual(self.tokens["--color-seat-1"], "var(--color-accent)")
        self.assertEqual(len(set(self.palette)), len(self.palette))
        self.assertGreaterEqual(len(self.palette), 3)

    def test_white_text_reads_on_every_colour_and_every_colour_stands_out_on_the_card(self):
        on_colour = hex_colour(self.tokens, "--color-on-accent")
        self.assertEqual(on_colour, "#ffffff")
        for colour in self.palette:
            with self.subTest(colour=colour):
                self.assertGreaterEqual(contrast(on_colour, colour), 4.5)
                for ground in ("--color-surface", "--color-bg"):
                    self.assertGreaterEqual(contrast(colour, hex_colour(self.tokens, ground)), 3)

    def test_the_colours_differ_in_lightness_with_every_kind_of_sight(self):
        for sight in ("normal", *DEFICIENCIES):
            values = []
            for colour in self.palette:
                rgb = linear_rgb(colour)
                values.append(lightness(rgb if sight == "normal" else seen_with(rgb, sight)))
            for first in range(len(values)):
                for second in range(first + 1, len(values)):
                    with self.subTest(sight=sight, first=self.palette[first], second=self.palette[second]):
                        self.assertGreaterEqual(abs(values[first] - values[second]), LIGHTNESS_GAP)

    def test_no_colour_of_a_seat_is_a_colour_of_the_dietary_flags(self):
        flags = {hex_colour(self.tokens, name) for name in self.tokens if name.startswith("--color-flag")}
        self.assertTrue(flags)
        self.assertEqual(flags & set(self.palette), set())

    def test_the_check_tells_a_bad_palette(self):
        for old, new in (("--color-seat-3: #2e8442;", "--color-seat-3: #3a9a50;"),   # white text too light
                         ("--color-seat-2: #481828;", "--color-seat-2: #1f4f6a;"),   # the lightness of the accent
                         ("--color-seat-2: #481828;", "--color-seat-2: #b45309;")):  # the dietary orange
            with self.subTest(token=new):
                self.assertEqual(self.css.count(old), 1)
                palette = seat_palette(self.css.replace(old, new))
                on_colour = hex_colour(self.tokens, "--color-on-accent")
                flags = {hex_colour(self.tokens, name) for name in self.tokens if name.startswith("--color-flag")}
                gaps = [abs(lightness(linear_rgb(a)) - lightness(linear_rgb(b)))
                        for k, a in enumerate(palette) for b in palette[k + 1:]]
                self.assertTrue(min(contrast(on_colour, colour) for colour in palette) < 4.5
                                or min(gaps) < LIGHTNESS_GAP or flags & set(palette))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
