"""Tests of the table plan geometry (`menu_tools._table`), standard library only.

The fixtures are fictional.  The L-shaped table is the one from the design
mockup; its seat centres with the per-side shifts match the mockup's
centres to the pixel.
"""

import ast
import copy
import hashlib
import inspect
import json
import re
import sys
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _table  # noqa: E402  (imported after sys.path is prepared)
from menu_tools._table import (  # noqa: E402
    TableCheck,
    TableError,
    badge_capacity,
    check_couple,
    check_table,
    expand_seats,
    guest_scheme,
    staff_scheme,
)

MODULE = ROOT / "menu_tools" / "_table.py"

COUPLE_LABEL = "Ivan · Vera"
COUPLE_TEXT = "IVAN · VERA"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def l_table() -> dict:
    """The mockup's L-shaped table of 16 seats, automatic layout."""
    return {
        "label": "L-shaped table",
        "arms": [
            {"id": "top", "x": 40, "y": 60, "width": 200, "height": 52},
            {"id": "right", "x": 188, "y": 60, "width": 52, "height": 200},
        ],
        "seats": [
            {"arm": "top", "side": "left"},                  # 1
            {"arm": "top", "side": "top", "count": 5},       # 2-6
            {"arm": "right", "side": "right", "count": 4},   # 7-10
            {"arm": "right", "side": "bottom"},              # 11
            {"arm": "right", "side": "left", "count": 2},    # 12-13
            {"arm": "top", "side": "bottom", "count": 3},    # 14-16
        ],
    }


def l_table_shifted() -> dict:
    """The same table with the side shifts that reproduce the mockup."""
    table = l_table()
    table["arms"][0]["shift"] = {"top": 10, "bottom": 5}
    table["arms"][1]["shift"] = {"right": 3, "left": -6}
    return table


def straight_table() -> dict:
    """A straight table of 12 seats: 5 + 5 on the long sides, one at each end."""
    return {
        "label": "Straight table",
        "arms": [{"id": "main", "x": 54, "y": 129, "width": 210, "height": 52}],
        "seats": [
            {"arm": "main", "side": "left"},
            {"arm": "main", "side": "top", "count": 5},
            {"arm": "main", "side": "right"},
            {"arm": "main", "side": "bottom", "count": 5},
        ],
    }


def u_table() -> dict:
    """A U-shaped table of 20 seats, open to the top."""
    return {
        "label": "U-shaped table",
        "arms": [
            {"id": "west", "x": 40, "y": 40, "width": 52, "height": 210},
            {"id": "base", "x": 40, "y": 198, "width": 238, "height": 52},
            {"id": "east", "x": 226, "y": 40, "width": 52, "height": 210},
        ],
        "seats": [
            {"arm": "west", "side": "top"},                  # 1
            {"arm": "west", "side": "right", "count": 2},    # 2-3
            {"arm": "base", "side": "top"},                  # 4
            {"arm": "east", "side": "left", "count": 2},     # 5-6
            {"arm": "east", "side": "top"},                  # 7
            {"arm": "east", "side": "right", "count": 4},    # 8-11
            {"arm": "base", "side": "bottom", "count": 5},   # 12-16
            {"arm": "west", "side": "left", "count": 4},     # 17-20
        ],
    }


def two_tables() -> dict:
    """Two separate tables of 8 seats each, numbered consecutively."""
    seats = []
    for arm in ("first", "second"):
        seats += [
            {"arm": arm, "side": "left"},
            {"arm": arm, "side": "top", "count": 3},
            {"arm": arm, "side": "right"},
            {"arm": arm, "side": "bottom", "count": 3},
        ]
    return {
        "label": "Two tables",
        "arms": [
            {"id": "first", "x": 91, "y": 40, "width": 136, "height": 48},
            {"id": "second", "x": 91, "y": 200, "width": 136, "height": 48},
        ],
        "seats": seats,
    }


def couple(seats=(4, 5), label=COUPLE_LABEL, arm=None) -> dict:
    return {"couple_seats": list(seats), "couple_label": label, "couple_arm": arm}


NO_COUPLE = couple((), None)

#: fixture -> (table, couple (of the staff plan), guest seats, staff letters)
FIXTURES = {
    "l-auto": (l_table, couple(), [8, 9], {1: ["A"], 3: ["N"], 7: ["V"], 10: ["G", "L"], 12: ["N", "V"]}),
    "l-shifted": (l_table_shifted, couple(), [8, 9], {1: ["A"], 10: ["G", "L"], 14: ["L"]}),
    "straight": (straight_table, couple((4, 10)), [7, 8], {2: ["N"], 7: ["G", "V"], 12: ["A"]}),
    "u": (u_table, couple((14, 15), arm="base"), [11, 12], {1: ["N"], 8: ["G", "L"], 20: ["A", "N"]}),
    "two": (two_tables, couple((3, 7)), [12, 13], {1: ["A"], 5: ["N", "G"], 14: ["V"]}),
}

#: The mockup's seat centres (px).
MOCKUP_CENTRES = {
    1: (18, 86), 2: (66, 38), 3: (108, 38), 4: (150, 38), 5: (192, 38), 6: (234, 38),
    7: (262, 100), 8: (262, 142), 9: (262, 184), 10: (262, 226), 11: (214, 282),
    12: (166, 212), 13: (166, 170), 14: (150, 134), 15: (108, 134), 16: (66, 134),
}

#: The automatic layout of the L-shaped table against the mockup (px): the
#: mockup was placed by hand and follows no single rule; the ends match.
AUTO_DEVIATIONS = {
    **{n: (-10, 0) for n in range(2, 7)},
    **{n: (0, -3) for n in range(7, 11)},
    12: (0, 6), 13: (0, 6),
    **{n: (-5, 0) for n in range(14, 17)},
}

OUTLINES = {
    "l-auto": (
        "M50 60L230 60A10 10 0 0 1 240 70L240 250A10 10 0 0 1 230 260L198 260"
        "A10 10 0 0 1 188 250L188 112L50 112A10 10 0 0 1 40 102L40 70A10 10 0 0 1 50 60Z"
    ),
    "straight": (
        "M64 129L254 129A10 10 0 0 1 264 139L264 171A10 10 0 0 1 254 181L64 181"
        "A10 10 0 0 1 54 171L54 139A10 10 0 0 1 64 129Z"
    ),
    "u": (
        "M50 40L82 40A10 10 0 0 1 92 50L92 198L226 198L226 50A10 10 0 0 1 236 40L268 40"
        "A10 10 0 0 1 278 50L278 240A10 10 0 0 1 268 250L50 250A10 10 0 0 1 40 240"
        "L40 50A10 10 0 0 1 50 40Z"
    ),
    "two": (
        "M101 40L217 40A10 10 0 0 1 227 50L227 78A10 10 0 0 1 217 88L101 88"
        "A10 10 0 0 1 91 78L91 50A10 10 0 0 1 101 40Z"
        "M101 200L217 200A10 10 0 0 1 227 210L227 238A10 10 0 0 1 217 248L101 248"
        "A10 10 0 0 1 91 238L91 210A10 10 0 0 1 101 200Z"
    ),
}

#: sha256 of the guest and staff objects of all FIXTURES (JSON, sorted keys).
DIGEST = "652ff1dba39af350a133414cdd20c83143b0815e26691b79bc60ae9c1db13a6a"


def guest(table, own, *, text="text", **width) -> dict:
    return guest_scheme(table, own_seats=list(own), plan_text=text, **width)


def staff(table, letters, *, pair=None) -> dict:
    return staff_scheme(table, letters=letters, **(couple() if pair is None else pair))


def fixture_objects(name: str) -> tuple[dict, dict]:
    make, pair, own, letters = FIXTURES[name]
    mine = ", ".join(f"guest {position}" for position, _number in enumerate(own, 1))
    return (
        guest(make(), own, text=mine),
        staff(make(), letters, pair=pair),
    )


def centres(scheme: dict) -> dict[int, tuple[str, str]]:
    return {int(seat["number"]): (seat["cx"], seat["cy"]) for seat in scheme["seats"]}


def px(value) -> str:
    return str(value)


def expanded(table: dict) -> dict:
    """The same table with one item per seat (no `count`)."""
    copy_ = copy.deepcopy(table)
    copy_["seats"] = []
    for item in table["seats"]:
        for k in range(item.get("count", 1)):
            seat = {"arm": item["arm"], "side": item["side"]}
            if "align" in item:
                seat["align"] = [item["align"][k]]
            copy_["seats"].append(seat)
    return copy_


def changed(make, change):
    def build():
        table = make()
        change(table)
        return table
    return build


def set_item(path, value):
    def change(table):
        target = table
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return change


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


class LayoutTest(unittest.TestCase):
    def test_shifted_l_table_matches_the_mockup(self):
        expected = {n: (px(x), px(y)) for n, (x, y) in MOCKUP_CENTRES.items()}
        self.assertEqual(centres(guest(l_table_shifted(), [8])), expected)

    def test_automatic_l_table_has_the_documented_deviations(self):
        expected = {}
        for n, (x, y) in MOCKUP_CENTRES.items():
            dx, dy = AUTO_DEVIATIONS.get(n, (0, 0))
            expected[n] = (px(x + dx), px(y + dy))
        self.assertEqual(centres(guest(l_table(), [8])), expected)

    def test_end_seats_sit_at_the_middle_of_the_ends(self):
        for make in (l_table, l_table_shifted):
            with self.subTest(table=make.__name__):
                found = centres(guest(make(), [8]))
                self.assertEqual(found[1], ("18", "86"))
                self.assertEqual(found[11], ("214", "282"))

    def test_seats_go_clockwise_on_every_side(self):
        found = {n: tuple(map(Fraction, centre)) for n, centre in centres(guest(l_table(), [8])).items()}
        self.assertLess(found[2][0], found[6][0])        # top: left to right
        self.assertLess(found[7][1], found[10][1])       # right: downwards
        self.assertGreater(found[12][1], found[13][1])   # left: upwards
        self.assertGreater(found[14][0], found[16][0])   # bottom: right to left

    def test_expand_seats_lists_arm_and_side_by_number(self):
        self.assertEqual(
            expand_seats(l_table()),
            [("top", "left")] + [("top", "top")] * 5 + [("right", "right")] * 4
            + [("right", "bottom")] + [("right", "left")] * 2 + [("top", "bottom")] * 3,
        )

    def test_count_and_the_expanded_list_give_the_same_result(self):
        for name, (make, pair, own, letters) in FIXTURES.items():
            with self.subTest(fixture=name):
                table = make()
                self.assertEqual(expand_seats(table), expand_seats(expanded(table)))
                self.assertEqual(guest(table, own), guest(expanded(table), own))
                self.assertEqual(staff(table, letters, pair=pair), staff(expanded(table), letters, pair=pair))

    def test_free_part_of_a_side_steps_back_from_a_neighbour_arm(self):
        table = l_table()
        table["seats"] = [{"arm": "top", "side": "bottom"}, {"arm": "right", "side": "left"}]
        found = centres(guest(table, [1]))
        # top arm, bottom side: 40 ... 188 - 22; right arm, left side: 112 + 22 ... 260
        self.assertEqual(found[1], ("103", "134"))
        self.assertEqual(found[2], ("166", "197"))

    def test_side_covered_by_another_arm_is_an_error(self):
        table = {
            "label": "T-shaped table",
            "arms": [
                {"id": "stem", "x": 100, "y": 40, "width": 60, "height": 60},
                {"id": "bar", "x": 60, "y": 80, "width": 160, "height": 50},
            ],
            "seats": [{"arm": "bar", "side": "bottom"}, {"arm": "stem", "side": "bottom"}],
        }
        self.assertEqual(
            check_table(table).errors,
            ["table.arms[0] side 'bottom': covered by another arm, no room for seat 2"],
        )

    def test_side_split_in_two_by_another_arm_is_an_error(self):
        table = {
            "label": "Table with a leg",
            "arms": [
                {"id": "long", "x": 40, "y": 100, "width": 240, "height": 50},
                {"id": "leg", "x": 140, "y": 130, "width": 40, "height": 100},
            ],
            "seats": [{"arm": "long", "side": "bottom", "count": 2}],
        }
        self.assertEqual(
            check_table(table).errors,
            ["table.arms[0] side 'bottom': split in two by another arm; make two arms of it (seats 1, 2)"],
        )

    def test_pitch_is_42_while_the_seats_fit_and_squeezed_down_to_34(self):
        def row(width, count):
            table = {
                "label": "Row",
                "arms": [{"id": "main", "x": 59, "y": 129, "width": width, "height": 52}],
                "seats": [{"arm": "main", "side": "top", "count": count}],
            }
            check = check_table(table)
            xs = [centre[0] for _, centre in sorted(centres(guest(table, [1])).items())]
            return check, xs

        check, xs = row(200, 5)
        self.assertEqual((check.errors, check.warnings), ([], []))
        self.assertEqual(xs, ["75", "117", "159", "201", "243"])
        check, xs = row(200, 6)
        self.assertEqual(check.errors, [])
        self.assertEqual(check.warnings, ["table.arms[0] side 'top': seats 1-6 squeezed closer than 42 px"])
        self.assertEqual(xs, ["74", "108", "142", "176", "210", "244"])
        check, xs = row(203, 6)  # a pitch of 34.5 px
        self.assertEqual(xs, ["74", "108.5", "143", "177.5", "212", "246.5"])

    def test_seven_seats_on_a_side_of_200_px_is_an_error(self):
        table = l_table()
        table["seats"][1]["count"] = 7
        self.assertEqual(
            check_table(table).errors,
            ["table.arms[0] side 'top': too short for seats 2-8: 7 seat(s) need 234 px of free length"],
        )


# --------------------------------------------------------------------------
# Seats lined up with other seats (align)
# --------------------------------------------------------------------------


def thin_l_table(aligned: bool = True) -> dict:
    """An L-shaped table of 19 seats with arms 44 px thick.  Aligned: seat 8
    faces seat 1 across the table, seat 7 sits over seat 12 at the end of the
    short arm, seats 13 and 14 inside the short arm face seats 11 and 10."""
    seats = [
        {"arm": "long", "side": "left"},                  # 1
        {"arm": "long", "side": "top", "count": 6},       # 2-7
        {"arm": "short", "side": "right", "count": 4},    # 8-11
        {"arm": "short", "side": "bottom"},               # 12
        {"arm": "short", "side": "left", "count": 2},     # 13-14
        {"arm": "long", "side": "bottom", "count": 5},    # 15-19
    ]
    if aligned:
        seats[1]["align"] = [None, None, None, None, None, 12]
        seats[2]["align"] = [1, None, None, None]
        seats[4]["align"] = [11, 10]
    return {
        "label": "L-shaped table",
        "arms": [
            {"id": "long", "x": 39, "y": 40, "width": 240, "height": 44},
            {"id": "short", "x": 235, "y": 40, "width": 44, "height": 170},
        ],
        "seats": seats,
    }


#: The automatic layout of the thin L-shaped table (px).
THIN_CENTRES = {
    1: (17, 62),
    **{n: (54 + 42 * (n - 2), 18) for n in range(2, 8)},
    **{n: (301, 62 + 42 * (n - 8)) for n in range(8, 12)},
    12: (257, 232), 13: (213, 179), 14: (213, 137),
    **{n: (198 - 36 * (n - 15), 106) for n in range(15, 20)},
}

#: The same table with its seats aligned (px).
ALIGNED_CENTRES = {
    **THIN_CENTRES,
    2: (54.5, 18), 3: (95, 18), 4: (135.5, 18), 5: (176, 18), 6: (216.5, 18), 7: (257, 18),
    13: (213, 188), 14: (213, 146),
}

SQUEEZED_BOTTOM = "table.arms[0] side 'bottom': seats 15-19 squeezed closer than 42 px"
SQUEEZED_TOP = "table.arms[0] side 'top': seats 2-7 squeezed closer than 42 px"


def thin_centres(table: dict) -> dict[int, tuple[str, str]]:
    return centres(guest(table, [1]))


def expected_centres(found: dict) -> dict[int, tuple[str, str]]:
    return {n: (px(x), px(y)) for n, (x, y) in found.items()}


def thin_with(path, value):
    return changed(thin_l_table, set_item(path, value))


#: (table, errors): every error of `align`, with the whole list of messages.
ALIGN_CASES = [
    (thin_with(["seats", 2, "align"], 1),
     ["table.seats[2].align (seats 8-11): expected an array of 4 elements: a seat number or null for each seat"]),
    (thin_with(["seats", 2, "align"], [1]),
     ["table.seats[2].align (seats 8-11): expected an array of 4 elements: a seat number or null for each seat"]),
    (thin_with(["seats", 3, "align"], []),
     ["table.seats[3].align (seat 12): expected an array of one element: a seat number or null"]),
    (thin_with(["seats", 2], {"arm": "short", "side": "right", "count": 0, "align": {}}), [
        "table.seats[2].count (seats from 8): expected an integer from 1 to 20",
        "table.seats[2].align (seats from 8): expected an array: a seat number or null for each seat",
    ]),
    (thin_with(["seats", 2, "align"], [0, "1", 1.0, True]), [
        "table.seats[2].align[0] (seat 8): expected a seat number or null",
        "table.seats[2].align[1] (seat 9): expected a seat number or null",
        "table.seats[2].align[2] (seat 10): expected a seat number or null",
        "table.seats[2].align[3] (seat 11): expected a seat number or null",
    ]),
    (thin_with(["seats", 2, "align"], [20, None, None, None]),
     ["table.seats[2].align[0] (seat 8): refers to no seat: the table has 19 seats"]),
    (thin_with(["seats", 2, "align"], [8, None, None, None]),
     ["table.seats[2].align[0] (seat 8): refers to the seat itself"]),
    (thin_with(["seats", 2, "align"], [None, None, None, 8]),
     ["table.seats[2].align[3] (seat 11): refers to seat 8 on the same side of the same arm"]),
    # an item of its own on the same side
    (changed(lambda: expanded(thin_l_table()), set_item(["seats", 8, "align"], [8])),
     ["table.seats[8].align[0] (seat 9): refers to seat 8 on the same side of the same arm"]),
    (thin_with(["seats", 0, "align"], [8]),
     ["table.seats[0].align[0] (seat 1): the alignment goes round in a circle through seats 1, 8"]),
    (changed(thin_l_table, lambda t: (
        set_item(["seats", 0, "align"], [8])(t),
        set_item(["seats", 2, "align"], [13, None, None, None])(t),
        set_item(["seats", 4, "align"], [1, None])(t),
    )), ["table.seats[0].align[0] (seat 1): the alignment goes round in a circle through seats 1, 8, 13"]),
    # through a seat placed by an aligned seat: 1 to 13, 13 to 11, 11 follows 8, 8 to 1
    (thin_with(["seats", 0, "align"], [13]),
     ["table.seats[0].align[0] (seat 1): the alignment goes round in a circle through seats 1, 8, 11, 13"]),
    # into the corner kept free between the arms
    (thin_with(["seats", 4, "align"], [11, 8]),
     ["table.seats[4].align[1] (seat 14): lines the seat up off the free part of its side"]),
    # past the end of the table
    (thin_with(["seats", 1, "align"], [None, None, None, None, None, 8]),
     ["table.seats[1].align[5] (seat 7): lines the seat up off the free part of its side"]),
    (thin_with(["seats", 4, "align"], [10, 11]),
     ["table.seats[4].align[1] (seat 14): puts the seat at or before seat 13, "
      "against the clockwise order of its side"]),
    (thin_with(["seats", 4, "align"], [11, 11]),
     ["table.seats[4].align[1] (seat 14): puts the seat at or before seat 13, "
      "against the clockwise order of its side"]),
    # seat 14 at the start of its free part, next to seat 15 of the long arm
    (thin_with(["seats", 4, "align"], [11, 18]), ["seats 14 and 15: closer than 34 px"]),
]


class AlignTest(unittest.TestCase):
    def test_aligned_seats_take_the_coordinate_of_their_seats(self):
        found = thin_centres(thin_l_table())
        self.assertEqual(found[8][1], found[1][1])
        self.assertEqual(found[13][1], found[11][1])
        self.assertEqual(found[14][1], found[10][1])
        self.assertEqual(found[7][0], found[12][0])
        # seat 12 in the middle of the short arm's end: (235 + 279) / 2
        self.assertEqual(found[12], ("257", "232"))

    def test_layout_of_the_aligned_table(self):
        table = thin_l_table()
        self.assertEqual(check_table(table), TableCheck([], [SQUEEZED_BOTTOM, SQUEEZED_TOP], 19))
        self.assertEqual(thin_centres(table), expected_centres(ALIGNED_CENTRES))

    def test_without_align_the_layout_stays_automatic(self):
        table = thin_l_table(aligned=False)
        self.assertEqual(check_table(table), TableCheck([], [SQUEEZED_BOTTOM], 19))
        self.assertEqual(thin_centres(table), expected_centres(THIN_CENTRES))
        nulls = thin_l_table(aligned=False)
        for item in nulls["seats"]:
            item["align"] = [None] * item.get("count", 1)
        self.assertEqual(check_table(nulls), check_table(table))
        self.assertEqual(guest(nulls, [8, 9]), guest(table, [8, 9]))
        self.assertEqual(staff(nulls, {10: ["G"]}, pair=NO_COUPLE), staff(table, {10: ["G"]}, pair=NO_COUPLE))

    def test_guest_and_staff_schemes_share_the_coordinates(self):
        table = thin_l_table()
        expected = expected_centres(ALIGNED_CENTRES)
        for number in range(1, 20):
            with self.subTest(seat=number):
                self.assertEqual(centres(guest(table, [number])), expected)
        self.assertEqual(centres(staff(table, {7: ["A"], 13: ["N", "V"]}, pair=NO_COUPLE)), expected)

    def test_seats_before_an_aligned_seat_that_do_not_fit_are_spread_up_to_the_end(self):
        # 42 px to the left of seat 7 would put seat 2 at 47, past 39 + 15
        found = thin_centres(thin_l_table())
        self.assertEqual([found[n][0] for n in range(2, 8)], ["54.5", "95", "135.5", "176", "216.5", "257"])

    def test_seats_after_an_aligned_seat_follow_it_at_42_px(self):
        # seat 8 faces seat 6 across the east arm: 5 px lower than without align
        table = u_table()
        table["seats"][5]["align"] = [6, None, None, None]
        self.assertEqual(check_table(table).errors, [])
        found = centres(guest(table, [1]))
        self.assertEqual([found[n][1] for n in range(8, 12)], ["87", "129", "171", "213"])
        self.assertEqual(found[8][1], found[6][1])

    def test_seats_after_an_aligned_seat_that_do_not_fit_are_spread_up_to_the_end(self):
        # seat 8 faces seat 5: 42 px below it seat 11 would come to 255, past 250 - 15
        table = u_table()
        table["seats"][5]["align"] = [5, None, None, None]
        self.assertEqual(
            check_table(table),
            TableCheck([], ["table.arms[2] side 'right': seats 8-11 squeezed closer than 42 px"], 20),
        )
        found = centres(guest(table, [1]))
        self.assertEqual([found[n][1] for n in range(8, 12)], ["129", "164", "199", "234"])
        self.assertEqual(found[8][1], found[5][1])

    def test_a_side_with_aligned_seats_is_reported_squeezed_once(self):
        # seat 19 under seat 2: the bottom side is squeezed as without align
        table = thin_l_table(aligned=False)
        table["seats"][5]["align"] = [None, None, None, None, 2]
        self.assertEqual(check_table(table), TableCheck([], [SQUEEZED_BOTTOM], 19))
        found = thin_centres(table)
        self.assertEqual([found[n][0] for n in range(15, 20)], ["198", "162", "126", "90", "54"])
        self.assertEqual(found[19][0], found[2][0])

    def test_seats_between_two_aligned_seats_are_spread_evenly(self):
        table = thin_l_table()
        table["seats"][1]["align"] = [19, None, None, None, None, 12]
        check = check_table(table)
        self.assertEqual(check.errors, [])
        self.assertIn(SQUEEZED_TOP, check.warnings)
        found = thin_centres(table)
        self.assertEqual([found[n][0] for n in range(2, 8)], ["54", "94.5", "135", "175.5", "216", "257"])
        self.assertEqual(found[2][0], found[19][0])

    def test_a_seat_may_align_to_a_later_seat_and_in_a_chain(self):
        # seat 2 faces seat 6, which faces seat 8: both come after it
        table = u_table()
        table["seats"][1]["align"] = [6, None]
        table["seats"][3]["align"] = [None, 8]
        self.assertEqual(check_table(table).errors, [])
        found = centres(guest(table, [1]))
        self.assertEqual({found[n][1] for n in (2, 6, 8)}, {"82"})
        self.assertEqual((found[3][1], found[5][1]), ("124", "124"))
        self.assertEqual(found[8][1], centres(guest(u_table(), [1]))[8][1])

    def test_the_shift_of_a_side_with_aligned_seats_has_no_effect(self):
        shifted = thin_l_table()
        shifted["arms"][1]["shift"] = {"right": 10}
        self.assertEqual(thin_centres(shifted), thin_centres(thin_l_table()))
        plain = thin_l_table(aligned=False)
        plain["arms"][1]["shift"] = {"right": 10}
        self.assertEqual(thin_centres(plain)[8], ("301", "72"))

    def test_count_and_the_expanded_list_give_the_same_result_with_align(self):
        table = thin_l_table()
        self.assertEqual(check_table(expanded(table)), check_table(table))
        self.assertEqual(guest(expanded(table), [13, 14]), guest(table, [13, 14]))
        self.assertEqual(staff(expanded(table), {7: ["A"]}, pair=NO_COUPLE),
                         staff(table, {7: ["A"]}, pair=NO_COUPLE))

    def test_every_error_of_align(self):
        for make, messages in ALIGN_CASES:
            with self.subTest(messages=messages):
                self.assertEqual(check_table(make()).errors, messages)

    def test_labels_follow_the_aligned_seats(self):
        # seat 14 sits 9 px lower than without align, its "You" label too
        plain = guest(thin_l_table(aligned=False), [14])["labels"]
        aligned = guest(thin_l_table(), [14])["labels"]
        self.assertEqual(len(plain), 1)
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["x"], plain[0]["x"])
        self.assertEqual(Fraction(aligned[0]["y"]) - Fraction(plain[0]["y"]), 9)


# --------------------------------------------------------------------------
# Outline
# --------------------------------------------------------------------------


class OutlineTest(unittest.TestCase):
    def test_outlines_of_the_shapes(self):
        for name, expected in OUTLINES.items():
            with self.subTest(shape=name):
                guest_object, staff_object = fixture_objects(name)
                self.assertEqual(guest_object["outline"], expected)
                self.assertEqual(staff_object["outline"], expected)

    def test_short_edges_get_a_smaller_radius_in_half_pixels(self):
        table = {
            "label": "Stepped table",
            "arms": [
                {"id": "top", "x": 40, "y": 60, "width": 200, "height": 52},
                {"id": "right", "x": 188, "y": 65, "width": 57, "height": 195},
            ],
            "seats": [{"arm": "top", "side": "top", "count": 3}, {"arm": "right", "side": "right", "count": 2}],
        }
        self.assertEqual(
            staff(table, {}, pair=NO_COUPLE)["outline"],
            "M50 60L237.5 60A2.5 2.5 0 0 1 240 62.5L240 65L242.5 65A2.5 2.5 0 0 1 245 67.5"
            "L245 250A10 10 0 0 1 235 260L198 260A10 10 0 0 1 188 250L188 112L50 112"
            "A10 10 0 0 1 40 102L40 70A10 10 0 0 1 50 60Z",
        )


# --------------------------------------------------------------------------
# The label "You" and the colours of a guest's seats
# --------------------------------------------------------------------------


def label_spots(scheme: dict) -> list[tuple[str, str, str]]:
    return [(label["x"], label["y"], label["anchor"]) for label in scheme["labels"]]


def narrow_table() -> dict:
    """One arm 20 px wide near the left edge: 2 seats on the right, 4 on the left."""
    return {
        "label": "Narrow table",
        "arms": [{"id": "main", "x": 48, "y": 37, "width": 20, "height": 233}],
        "seats": [{"arm": "main", "side": "right", "count": 2}, {"arm": "main", "side": "left", "count": 4}],
    }


class LabelTest(unittest.TestCase):
    def test_you_next_to_seat_8_as_in_the_mockup(self):
        scheme = guest(l_table_shifted(), [8])
        self.assertEqual(scheme["labels"], [{"x": "283", "y": "142", "anchor": "start"}])

    def test_labels_fall_back_at_the_edge_of_the_field(self):
        # seat 1: outwards (left) is out of the field, right lies on the arm
        self.assertEqual(label_spots(guest(l_table(), [1])), [("18", "58", "middle")])
        # seat 11: outwards (down) is out of the field
        self.assertEqual(label_spots(guest(l_table(), [11])), [("235", "282", "start")])

    def test_label_at_the_inner_corner_may_lie_on_an_arm(self):
        # seat 14: below is seat 13, left is seat 15; the label goes onto the right arm
        self.assertEqual(label_spots(guest(l_table(), [14])), [("166", "134", "start")])

    def test_every_seat_of_the_l_table_has_room_for_you(self):
        # the couple's seats on the staff plan too: the guest plan has no couple
        for make in (l_table, l_table_shifted):
            for number in range(1, 17):
                with self.subTest(table=make.__name__, seat=number):
                    labels = guest(make(), [number])["labels"]
                    self.assertEqual(len(labels), 1)
                    self.assertEqual(set(labels[0]), {"x", "y", "anchor"})

    def test_a_record_of_more_seats_gets_no_label(self):
        # the colours tell the seats apart
        for own in ([8, 9], [9, 8], [8, 9, 10]):
            with self.subTest(own=own):
                scheme = guest(l_table(), own)
                self.assertEqual(scheme["labels"], [])
                self.assertEqual([s["kind"] for s in scheme["seats"]].count("you"), len(own))

    def test_the_box_of_the_label_follows_the_word(self):
        # 7 px a character and 4 px more, never narrower than the box of "You"
        self.assertEqual(_table.label_box_width("You"), _table.MIN_LABEL_WIDTH)
        self.assertEqual((_table.label_box_width("Vi"), _table.label_box_width("Vous")), (26, 32))
        self.assertEqual(_table.label_box_width("Ovde sedite vi"), 102)
        # the box of "You" fits at every seat; a long word does not
        long = _table.label_box_width("Ovde sedite vi")
        self.assertEqual(check_table(l_table(), label_width=_table.label_box_width("You")).errors, [])
        errors = check_table(l_table(), label_width=long).errors
        self.assertTrue(errors)
        self.assertEqual({message.split(": ", 1)[1] for message in errors}, {"no room for the label of the guest's seat"})
        # a plan that has no room for the label is never laid out
        with self.assertRaises(TableError):
            guest(l_table(), [8], label_width=long)
        self.assertEqual(len(guest(l_table(), [8], label_width=_table.MIN_LABEL_WIDTH)["labels"]), 1)

    def test_a_label_at_the_edge_of_the_field_lies_on_a_narrow_arm(self):
        # seat 5 at the left edge: outwards is out of the field, up and down
        # are the next seats; the label goes right onto the arm 20 px wide
        table = narrow_table()
        self.assertEqual(check_table(table).errors, [])
        self.assertEqual(label_spots(guest(table, [5])), [("47", "132.5", "start")])
        self.assertEqual(label_spots(guest(table, [4])), [("47", "174.5", "start")])


class ColourTest(unittest.TestCase):
    def test_each_seat_of_the_guest_takes_the_colour_of_its_place_in_the_record(self):
        self.assertEqual(_table.SEAT_COLOURS, ("1", "2", "3"))
        for own in ([8], [9, 8], [14, 8, 3]):
            with self.subTest(own=own):
                scheme = guest(l_table(), own)
                colours = {int(seat["number"]): seat["colour"] for seat in scheme["seats"] if seat["colour"]}
                self.assertEqual(colours, dict(zip(own, _table.SEAT_COLOURS)))
                for seat in scheme["seats"]:
                    mine = int(seat["number"]) in own
                    self.assertEqual((seat["kind"], seat["ring"], seat["r"]),
                                     ("you", True, "16.25") if mine else ("regular", False, "14.25"))

    def test_more_seats_than_colours_is_an_error(self):
        with self.assertRaises(TableError) as caught:
            guest(l_table(), [8, 9, 10, 11])
        self.assertEqual(caught.exception.errors, ["own_seats: expected at most 3 seats, one per colour"])

    def test_the_guest_plan_has_no_couple(self):
        # the couple sits at seats 4 and 5 of the staff plan: plain seats for
        # a guest, no couple label; a couple seat in a record (refused by the
        # data checks) would take the guest's colour
        staff_object = staff(l_table(), {})
        self.assertEqual([seat["number"] for seat in staff_object["seats"] if seat["kind"] == "couple"], ["4", "5"])
        self.assertIsNotNone(staff_object["couple"])
        scheme = guest(l_table(), [8])
        self.assertIsNone(scheme["couple"])
        self.assertNotIn("couple", {seat["kind"] for seat in scheme["seats"]})
        scheme = guest(l_table(), [4])
        seat = scheme["seats"][3]
        self.assertEqual((seat["kind"], seat["colour"]), ("you", "1"))

    def test_the_staff_plan_has_no_colours(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _guest_object, staff_object = fixture_objects(name)
                self.assertEqual({seat["colour"] for seat in staff_object["seats"]}, {""})


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------


def badge_spots(scheme: dict) -> list[tuple[str, str]]:
    return [(badge["cx"], badge["cy"]) for badge in scheme["badges"]]


class BadgeTest(unittest.TestCase):
    def test_one_badge_at_the_top_right_as_in_the_mockup(self):
        scheme = staff(l_table_shifted(), {1: ["A"]})
        self.assertEqual(scheme["badges"], [{"letter": "A", "cx": "30", "cy": "74", "r": "9"}])

    def test_one_to_four_badges(self):
        expected = {
            1: [("274", "130")],
            2: [("250", "130"), ("274", "130")],
            3: [("250", "130"), ("274", "130"), ("274", "154")],
            4: [("250", "130"), ("274", "130"), ("250", "154"), ("274", "154")],
        }
        for count, spots in expected.items():
            with self.subTest(count=count):
                letters = list("ABCD"[:count])
                scheme = staff(l_table_shifted(), {8: letters})
                self.assertEqual(badge_spots(scheme), spots)
                self.assertEqual([badge["letter"] for badge in scheme["badges"]], letters)

    def test_two_badges_at_seat_10_sit_above_it(self):
        scheme = staff(l_table(), {10: ["G", "L"]})
        self.assertEqual(badge_spots(scheme), [("250", "211"), ("274", "211")])

    def test_badge_capacity_is_smaller_at_the_edge_of_the_field(self):
        self.assertEqual([badge_capacity(l_table(), n) for n in range(1, 17)], [2] + [4] * 15)
        self.assertEqual(
            [badge_capacity(u_table(), n) for n in range(1, 21)],
            [2, 4, 4, 4, 4, 4, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 2, 2, 2, 2],
        )
        # seat 1 of the L table: the left spots are outside the field
        self.assertEqual(badge_spots(staff(l_table(), {1: ["A", "B"]})), [("30", "74"), ("30", "98")])

    def test_more_badges_than_room_is_an_error(self):
        with self.assertRaises(TableError) as caught:
            staff(l_table(), {1: ["A", "B", "C"]})
        self.assertEqual(caught.exception.errors, ["seat 1: no room for 3 badges"])
        with self.assertRaises(TableError) as caught:
            staff(l_table(), {8: list("ABCDE")})
        self.assertEqual(caught.exception.errors, ["seat 8: no room for 5 badges"])


# --------------------------------------------------------------------------
# The couple
# --------------------------------------------------------------------------


def row_table() -> dict:
    """A row of 7 squeezed seats along the top edge of the field."""
    return {
        "label": "Row",
        "arms": [{"id": "main", "x": 40, "y": 56, "width": 238, "height": 30}],
        "seats": [{"arm": "main", "side": "top", "count": 7}],
    }


SEATS_ERROR = "couple.members[].seat: expected 1-2 different seat numbers from 1 to 16"
LABEL_ERROR = "couple.label: expected a non-empty one-line string"

#: (rule, table, check_couple arguments after the table, level, messages);
#: the rules are those of the table description that concern the couple.
COUPLE_CASES = [
    (15, l_table, ([4, 17], COUPLE_LABEL, None), "error", [SEATS_ERROR]),
    (15, l_table, ([4, 4], COUPLE_LABEL, None), "error", [SEATS_ERROR]),
    (15, l_table, ([1, 2, 3], COUPLE_LABEL, None), "error", [SEATS_ERROR]),
    (15, l_table, ([], COUPLE_LABEL, None), "error", [SEATS_ERROR]),
    (15, l_table, (["4"], COUPLE_LABEL, None), "error", [SEATS_ERROR]),
    (15, l_table, ([4, 5], COUPLE_LABEL, "middle"), "error", ["couple.arm: not an id of table.arms"]),
    (2, l_table, ([4, 5], "", None), "error", [LABEL_ERROR]),
    (2, l_table, ([4, 5], "Ivan\nVera", None), "error", [LABEL_ERROR]),
    (16, l_table, ([4, 5], "Ivan Ivanovich and Vera Longname", None), "warning",
     ["couple.label: may not fit inside the arm"]),
]


class CoupleTest(unittest.TestCase):
    def test_couple_label_in_the_middle_of_the_free_part_of_its_arm(self):
        for make in (l_table, l_table_shifted):
            with self.subTest(table=make.__name__):
                self.assertEqual(
                    staff(make(), {})["couple"], {"text": COUPLE_TEXT, "x": "114", "y": "86", "vertical": False}
                )

    def test_couple_label_on_a_vertical_arm(self):
        scheme = staff(l_table(), {}, pair=couple(arm="right"))
        self.assertEqual(scheme["couple"], {"text": COUPLE_TEXT, "x": "214", "y": "186", "vertical": True})

    def test_no_couple_label_without_a_label(self):
        scheme = staff(l_table(), {}, pair=couple(label=None))
        self.assertIsNone(scheme["couple"])
        self.assertEqual([s["kind"] for s in scheme["seats"]].count("couple"), 2)

    def test_check_couple_accepts_the_fixtures(self):
        for name, (make, pair, _own, _letters) in FIXTURES.items():
            with self.subTest(fixture=name):
                check = check_couple(make(), pair["couple_seats"], pair["couple_label"], pair["couple_arm"])
                self.assertEqual(check, TableCheck([], [], len(expand_seats(make()))))

    def test_check_couple_cases(self):
        for rule, make, args, level, messages in COUPLE_CASES:
            with self.subTest(rule=rule, args=args):
                check = check_couple(make(), *args)
                if level == "warning":
                    self.assertEqual((check.errors, check.warnings), ([], messages))
                else:
                    self.assertEqual(check.errors, messages)

    def test_couple_label_on_the_only_spot_of_a_you_label(self):
        # a squeezed row at the top of the field: the only room for a middle
        # seat's label is on the arm, where the couple label is; the two
        # never meet: the couple is on the staff plan alone, "You" on a
        # guest's plan alone
        self.assertEqual(check_table(row_table()).errors, [])
        self.assertEqual(label_spots(guest(row_table(), [3])), [("124.5", "62", "middle")])
        self.assertEqual(staff(row_table(), {}, pair=couple((4,)))["couple"],
                         {"text": COUPLE_TEXT, "x": "159", "y": "71", "vertical": False})
        for label in (None, COUPLE_LABEL):
            with self.subTest(label=label):
                self.assertEqual(check_couple(row_table(), [4], label, None), TableCheck([], [], 7))

    def test_check_couple_with_a_broken_table_checks_what_it_can(self):
        table = l_table()
        table["arms"][0]["width"] = "wide"
        # the seats are counted, the arms are not known: the arm is not checked
        self.assertEqual(
            check_couple(table, [4, 17], COUPLE_LABEL, "middle"),
            TableCheck(["couple.members[].seat: expected 1-2 different seat numbers from 1 to 16"], [], 16),
        )
        self.assertEqual(
            check_couple("table", [1, 2, 3], COUPLE_LABEL, None).errors,
            ["couple.members[].seat: expected 1-2 different seat numbers"],
        )


# --------------------------------------------------------------------------
# The field size
# --------------------------------------------------------------------------


def wide_l_table() -> dict:
    """An L-shaped table of 18 seats in a field of 360 x 310: one seat at the
    end of the long arm, 7 over it and 6 under it, lined up with the seats
    over it; 3 seats on the right of the short arm, the first one facing
    the seat at the end of the long arm, and one on its left facing the last
    of them.  The last seat of the top row sits over the middle of the short
    arm; both arms are 32 px thick."""
    return {
        "label": "L-shaped table",
        "width": 360,
        "height": 310,
        "arms": [
            {"id": "long", "x": 39, "y": 40, "width": 282, "height": 32, "shift": {"top": -1}},
            {"id": "short", "x": 289, "y": 40, "width": 32, "height": 120},
        ],
        "seats": [
            {"arm": "long", "side": "left"},                                                  # 1
            {"arm": "long", "side": "top", "count": 7},                                       # 2-8
            {"arm": "short", "side": "right", "count": 3, "align": [1, None, None]},          # 9-11
            {"arm": "short", "side": "left", "align": [11]},                                  # 12
            {"arm": "long", "side": "bottom", "count": 6, "align": [7, 6, 5, 4, 3, 2]},       # 13-18
        ],
    }


WIDE_CENTRES = {
    1: (17, 56), 2: (53, 18), 3: (95, 18), 4: (137, 18), 5: (179, 18), 6: (221, 18), 7: (263, 18),
    8: (305, 18), 9: (343, 56), 10: (343, 98), 11: (343, 140), 12: (267, 140),
    13: (263, 94), 14: (221, 94), 15: (179, 94), 16: (137, 94), 17: (95, 94), 18: (53, 94),
}


def sized(make, width=None, height=None):
    """A fixture with the size of its field given (None: left out)."""
    def build():
        table = make()
        for key, value in (("width", width), ("height", height)):
            table.pop(key, None)
            if value is not None:
                table[key] = value
        return table
    return build


class FieldTest(unittest.TestCase):
    def test_the_wide_l_table_fits_its_field(self):
        self.assertEqual(check_table(wide_l_table()), TableCheck([], [], 18))
        scheme = guest(wide_l_table(), [8])
        self.assertEqual((scheme["width"], scheme["height"]), ("360", "310"))
        self.assertEqual(centres(scheme), {n: (px(x), px(y)) for n, (x, y) in WIDE_CENTRES.items()})
        # seat 8 over the middle of the short arm
        short = wide_l_table()["arms"][1]
        self.assertEqual(WIDE_CENTRES[8][0], short["x"] + short["width"] // 2)
        # its label goes right, past the edge of the default field
        self.assertEqual(scheme["labels"], [{"x": "326", "y": "18", "anchor": "start"}])
        for number in range(1, 19):
            with self.subTest(seat=number):
                self.assertEqual(len(guest(wide_l_table(), [number])["labels"]), 1)
        self.assertEqual(staff(wide_l_table(), {15: list("ABCD")}, pair=NO_COUPLE)["width"], "360")

    def test_the_wide_l_table_needs_its_field(self):
        errors = check_table(sized(wide_l_table)()).errors
        self.assertEqual(errors, ["table.arms[0]: lies outside the 318x310 field",
                                  "table.arms[1]: lies outside the 318x310 field"])

    def test_the_default_size_is_318_x_310(self):
        self.assertEqual((_table.FIELD_WIDTH, _table.FIELD_HEIGHT), (318, 310))
        for name, (make, pair, own, letters) in FIXTURES.items():
            with self.subTest(fixture=name):
                given = sized(make, 318, 310)
                self.assertEqual(check_table(given()), check_table(make()))
                self.assertEqual(guest(given(), own), guest(make(), own))
                self.assertEqual(staff(given(), letters, pair=pair), staff(make(), letters, pair=pair))

    def test_the_edges_of_the_field_follow_its_size(self):
        # the right seats of the U table at the right edge: room for badges
        # and the label on the right in a wider field
        self.assertEqual([badge_capacity(u_table(), n) for n in range(8, 12)], [2] * 4)
        wide = sized(u_table, 360)
        self.assertEqual(check_table(wide()).errors, [])
        self.assertEqual([badge_capacity(wide(), n) for n in range(8, 12)], [4] * 4)
        cx, cy = centres(guest(wide(), [9]))[9]
        self.assertNotEqual(label_spots(guest(u_table(), [9]))[0][2], "start")
        self.assertEqual(label_spots(guest(wide(), [9])), [(str(int(cx) + 21), cy, "start")])
        # a lower field cuts the bottom seat of the L table off
        self.assertEqual(check_table(sized(l_table, height=290)()).errors,
                         ["table.seats[3] (seat 11): does not fit into the 318x290 field"])

    def test_the_limits_are_inclusive(self):
        for width, height in ((240, 160), (480, 640)):
            with self.subTest(width=width, height=height):
                table = {"label": "Small", "width": width, "height": height,
                         "arms": [{"id": "main", "x": 40, "y": 60, "width": 160, "height": 40}],
                         "seats": [{"arm": "main", "side": "top", "count": 3},
                                   {"arm": "main", "side": "bottom", "count": 3}]}
                self.assertEqual(check_table(table), TableCheck([], [], 6))
                self.assertEqual(guest(table, [1])["width"], str(width))


# --------------------------------------------------------------------------
# The table description check: every rule
# --------------------------------------------------------------------------


def close_tables() -> dict:
    return {
        "label": "Two tables close together",
        "arms": [
            {"id": "first", "x": 91, "y": 40, "width": 136, "height": 48},
            {"id": "second", "x": 91, "y": 125, "width": 136, "height": 48},
        ],
        "seats": [{"arm": "first", "side": "bottom", "count": 3}, {"arm": "second", "side": "bottom", "count": 3}],
    }


#: (rule, table, message); the rules are those of the table description.
RULE_CASES = [
    (1, lambda: [], "table: expected an object"),
    (1, changed(l_table, set_item(["couple"], {"seats": [4, 5]})),
     "table: unknown field (allowed: arms, height, label, seats, width)"),
    (1, changed(l_table, set_item(["arms", 1, "radius"], 4)),
     "table.arms[1]: unknown field (allowed: height, id, shift, width, x, y)"),
    (1, changed(l_table, set_item(["seats", 3, "number"], 11)),
     "table.seats[3] (seat 11): unknown field (allowed: align, arm, count, side)"),
    (2, changed(l_table, set_item(["label"], "")), "table.label: expected a non-empty one-line string"),
    (2, changed(l_table, set_item(["label"], "Two\nlines")), "table.label: expected a non-empty one-line string"),
    (3, changed(l_table, set_item(["arms"], [])), "table.arms: expected a non-empty array"),
    (3, changed(l_table, set_item(["arms", 0], "top")), "table.arms[0]: expected an object"),
    (3, changed(l_table, set_item(["arms", 0, "id"], "Top")),
     "table.arms[0].id: expected an id: a-z, 0-9 and '-', starting with a letter, at most 40 characters"),
    (3, changed(l_table, set_item(["arms", 1, "id"], "top")), "table.arms[1].id: repeats table.arms[0].id"),
    (3, changed(l_table, set_item(["arms", 0, "x"], 40.5)), "table.arms[0].x: expected an integer (px)"),
    (3, changed(l_table, set_item(["arms", 0, "height"], True)), "table.arms[0].height: expected an integer (px)"),
    (3, changed(l_table, set_item(["arms", 1, "width"], 19)), "table.arms[1].width: expected at least 20 px"),
    (3, changed(l_table, set_item(["arms", 0, "shift"], {"top": 43})),
     "table.arms[0].shift.top: expected an integer from -42 to 42"),
    (3, changed(l_table, set_item(["arms", 0, "shift"], {"middle": 1})),
     "table.arms[0].shift: unknown side (allowed: top, right, bottom, left)"),
    (3, changed(l_table, set_item(["arms", 0, "shift"], [10])),
     "table.arms[0].shift: expected an object with sides as keys"),
    (4, changed(l_table, set_item(["arms", 1, "height"], 251)), "table.arms[1]: lies outside the 318x310 field"),
    (4, changed(l_table, set_item(["arms", 0, "x"], -1)), "table.arms[0]: lies outside the 318x310 field"),
    (4, changed(l_table, set_item(["width"], 239)), "table.width: expected an integer from 240 to 480 (px)"),
    (4, changed(l_table, set_item(["width"], 481)), "table.width: expected an integer from 240 to 480 (px)"),
    (4, changed(l_table, set_item(["width"], 318.0)), "table.width: expected an integer from 240 to 480 (px)"),
    (4, changed(l_table, set_item(["height"], 159)), "table.height: expected an integer from 160 to 640 (px)"),
    (4, changed(l_table, set_item(["height"], 641)), "table.height: expected an integer from 160 to 640 (px)"),
    (4, changed(l_table, set_item(["height"], "310")), "table.height: expected an integer from 160 to 640 (px)"),
    (4, changed(l_table, set_item(["height"], 250)), "table.arms[1]: lies outside the 318x250 field"),
    (5, changed(l_table, lambda t: t["arms"].append({"id": "inner", "x": 60, "y": 70, "width": 40, "height": 30})),
     "table.arms[2]: lies inside table.arms[0]"),
    (5, changed(l_table, set_item(["arms", 1], {"id": "right", "x": 240, "y": 112, "width": 52, "height": 148})),
     "table.arms[0] and table.arms[1]: touch only at a corner"),
    (6, changed(l_table, set_item(["seats"], [])), "table.seats: expected a non-empty array"),
    (6, changed(l_table, set_item(["seats", 0], "top")), "table.seats[0] (seat 1): expected an object"),
    (6, changed(l_table, set_item(["seats", 0, "arm"], "middle")),
     "table.seats[0].arm (seat 1): not an id of table.arms"),
    (6, changed(l_table, set_item(["seats", 1, "side"], "start")),
     "table.seats[1].side (seats 2-6): expected one of top, right, bottom, left"),
    (6, changed(l_table, set_item(["seats", 1, "count"], 0)),
     "table.seats[1].count (seats from 2): expected an integer from 1 to 20"),
    (6, changed(l_table, set_item(["seats", 2, "count"], 21)),
     "table.seats[2].count (seats from 7): expected an integer from 1 to 20"),
    (7, changed(l_table, lambda t: t["arms"].append({"id": "leg", "x": 100, "y": 100, "width": 30, "height": 100})),
     "table.arms[0] side 'bottom': split in two by another arm; make two arms of it (seats 14-16)"),
    (8, changed(l_table, set_item(["seats", 1, "count"], 7)),
     "table.arms[0] side 'top': too short for seats 2-8: 7 seat(s) need 234 px of free length"),
    (9, changed(l_table, set_item(["seats", 1, "count"], 6)),
     "table.arms[0] side 'top': seats 2-7 squeezed closer than 42 px"),
    (10, changed(straight_table, set_item(["arms", 0, "x"], 30)),
     "table.seats[0] (seat 1): does not fit into the 318x310 field"),
    (10, changed(l_table, set_item(["height"], 280)),
     "table.seats[3] (seat 11): does not fit into the 318x280 field"),
    (11, changed(l_table, set_item(["arms", 0, "shift"], {"left": 42})),
     "table.seats[0] (seat 1): the shift moves it off its side"),
    (12, close_tables, "table.seats[0] (seat 1): touches an arm of the table"),
    (13, changed(l_table, set_item(["seats", 0], {"arm": "top", "side": "right"})),
     "seats 1 and 7: closer than 34 px"),
    (17, changed(l_table, set_item(["seats"], [{"arm": "top", "side": "top", "count": 20}] * 5)),
     "table.seats: at most 99 seats"),
]

WARNING_RULES = {9}

#: (rule, table, patched constants, messages): with the real constants a
#: seat's label can always go onto its own arm, so the rule is reached only
#: with a wider keep-out around the other seats.
PATCHED_RULE_CASES = [
    (14, l_table, {"SEAT_KEEP_OUT": 40}, [
        "table.seats[1] (seat 3): no room for the label of the guest's seat",
        "table.seats[5] (seat 14): no room for the label of the guest's seat",
    ]),
]


class CheckTest(unittest.TestCase):
    def test_fixtures_pass(self):
        for name, (make, _pair, _own, _letters) in FIXTURES.items():
            with self.subTest(fixture=name):
                self.assertEqual(check_table(make()), TableCheck([], [], len(expand_seats(make()))))

    def test_every_rule_has_a_negative_case(self):
        for rule, make, message in RULE_CASES:
            with self.subTest(rule=rule, message=message):
                check = check_table(make())
                found = check.warnings if rule in WARNING_RULES else check.errors
                self.assertIn(message, found)
                if rule in WARNING_RULES:
                    self.assertEqual(check.errors, [])

    def test_room_for_you_is_checked_for_every_seat(self):
        for rule, make, constants, messages in PATCHED_RULE_CASES:
            with self.subTest(rule=rule, constants=constants):
                with mock.patch.multiple(_table, **constants):
                    errors = check_table(make()).errors
                for message in messages:
                    self.assertIn(message, errors)
        self.assertEqual(check_table(l_table()).errors, [])

    def test_the_cases_cover_all_17_rules(self):
        covered = (
            {rule for rule, _, _ in RULE_CASES}
            | {rule for rule, *_ in COUPLE_CASES}
            | {rule for rule, *_ in PATCHED_RULE_CASES}
        )
        self.assertEqual(covered, set(range(1, 18)))

    def test_one_line_label_rejects_any_line_break(self):
        for label in ("Table\r", "Table" + chr(0x2028) + "plan", " ", 7, None):
            with self.subTest(label=label):
                table = l_table()
                table["label"] = label
                self.assertEqual(check_table(table).errors, ["table.label: expected a non-empty one-line string"])

    def test_total_is_none_only_when_the_seats_cannot_be_read(self):
        self.assertIsNone(check_table("table").total)
        self.assertIsNone(check_table(changed(l_table, set_item(["seats", 1, "count"], "5"))()).total)
        self.assertIsNone(check_table(changed(l_table, set_item(["seats", 0], 1))()).total)
        self.assertEqual(check_table(changed(l_table, set_item(["arms", 0, "x"], "40"))()).total, 16)
        self.assertEqual(check_table(changed(l_table, set_item(["seats", 0, "arm"], "x"))()).total, 16)


#: A table whose ids, label and numbers are easy to spot in a message.
def secret_table() -> dict:
    return {
        "label": "Qzlabel 777",
        "arms": [{"id": "qzarm", "x": 57, "y": 131, "width": 203, "height": 51, "shift": {"top": 13}}],
        "seats": [
            {"arm": "qzarm", "side": "left"},
            {"arm": "qzarm", "side": "top", "count": 5},
            {"arm": "qzarm", "side": "right"},
            {"arm": "qzarm", "side": "bottom", "count": 5},
        ],
    }


SECRET_NUMBERS = {
    "57", "131", "203", "51", "260", "182", "13", "777", "157", "77", "33", "130", "19", "43", "253",
}

SECRET_CHANGES = [
    set_item(["qzfield"], 1),
    set_item(["arms", 0, "qzfield"], 1),
    set_item(["seats", 0, "qzfield"], 1),
    set_item(["label"], "Qzlabel\n777"),
    set_item(["arms", 0, "id"], "Qzarm"),
    lambda t: t["arms"].append(dict(t["arms"][0], y=19, height=43)),
    set_item(["arms", 0, "x"], "qz57"),
    set_item(["width"], 777),
    set_item(["height"], "qz777"),
    set_item(["arms", 0, "width"], 17),
    set_item(["arms", 0, "shift"], {"top": 77}),
    set_item(["arms", 0, "shift"], {"qzside": 1}),
    set_item(["arms", 0, "x"], 157),
    lambda t: t["arms"].append({"id": "qzin", "x": 77, "y": 133, "width": 33, "height": 43}),
    lambda t: t["arms"].append({"id": "qzcorner", "x": 260, "y": 182, "width": 33, "height": 43}),
    set_item(["seats", 0, "arm"], "qzother"),
    set_item(["seats", 0, "side"], "qzside"),
    set_item(["seats", 1, "count"], 33),
    set_item(["seats", 1, "count"], 7),
    set_item(["seats", 1, "count"], 6),
    lambda t: t["arms"].append({"id": "qzleg", "x": 130, "y": 160, "width": 33, "height": 77}),
    set_item(["arms", 0, "x"], 19),
    set_item(["arms", 0, "shift"], {"left": 33}),
    lambda t: t["arms"].append({"id": "qznear", "x": 77, "y": 50, "width": 130, "height": 43}),
    set_item(["seats", 0], {"arm": "qzarm", "side": "top"}),
    set_item(["seats"], [{"arm": "qzarm", "side": "top", "count": 20}] * 5),
    set_item(["seats", 1, "align"], "qz777"),
    set_item(["seats", 1, "align"], [None] * 7),
    set_item(["seats", 1, "align"], ["qz", 77, 1.5, None, None]),
    set_item(["seats", 1, "align"], [None, None, None, None, 7]),
    set_item(["seats", 2, "align"], [3]),
    set_item(["seats", 0, "align"], [2]),
    lambda t: (set_item(["seats", 0, "align"], [7])(t), set_item(["seats", 2, "align"], [1])(t)),
]


class MessageTest(unittest.TestCase):
    def test_messages_hold_no_ids_labels_or_numbers_of_the_data(self):
        messages = []
        for change in SECRET_CHANGES:
            table = secret_table()
            change(table)
            check = check_table(table)
            self.assertTrue(check.errors or check.warnings, f"no message for {change}")
            messages += check.errors + check.warnings
        for args in (([1, 77], "Qzlabel 777", None), ([1, 2], "Qzlabel", "qzother"),
                     ([1, 2], "Qzlabel\n777", None), ([1, 2], "Qzlabel " * 9, None)):
            check = check_couple(secret_table(), *args)
            self.assertTrue(check.errors or check.warnings, f"no message for {args}")
            messages += check.errors + check.warnings
        for message in messages:
            with self.subTest(message=message):
                self.assertNotIn("qz", message.lower())
                self.assertFalse(set(re.findall(r"\d+", message)) & SECRET_NUMBERS)


# --------------------------------------------------------------------------
# The scheme objects
# --------------------------------------------------------------------------

#: Keys whose values are numbers written as strings.
NUMBER_KEYS = {"width", "height", "total", "number", "cx", "cy", "r", "ringR", "x", "y"}
NUMBER_RE = re.compile(r"-?\d+(\.(5|25|75))?")


def walk(value):
    """(key, value) of every field in the nested dicts and lists."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


class SchemeTest(unittest.TestCase):
    def test_guest_object(self):
        table = l_table()
        table["label"] = 'L-shaped <table> & "co"'
        scheme = guest(table, [8, 9], text="the text of the caller")
        self.assertEqual(
            {key: scheme[key] for key in ("width", "height", "hidden", "planText")},
            {"width": "318", "height": "310", "hidden": False, "planText": "the text of the caller"},
        )
        self.assertEqual((scheme["badges"], scheme["labels"], scheme["couple"]), ([], [], None))
        self.assertEqual({seat["mark"] for seat in scheme["seats"]}, {"none"})
        self.assertEqual(
            scheme["seats"][7:9],
            [{"number": "8", "cx": "262", "cy": "139", "r": "16.25", "kind": "you", "mark": "none",
              "colour": "1", "ring": True, "ringR": "21"},
             {"number": "9", "cx": "262", "cy": "181", "r": "16.25", "kind": "you", "mark": "none",
              "colour": "2", "ring": True, "ringR": "21"}],
        )
        self.assertEqual(scheme["seats"][3]["kind"], "regular")
        self.assertEqual((scheme["seats"][0]["r"], scheme["seats"][0]["colour"]), ("14.25", ""))
        self.assertEqual(len(guest(l_table(), [3])["labels"]), 1)

    def test_staff_object(self):
        scheme = staff(l_table(), {10: ["G", "L"], 12: []})
        self.assertTrue(scheme["hidden"])
        self.assertEqual((scheme["planText"], scheme["labels"]), ("", []))
        self.assertNotIn("you", {seat["kind"] for seat in scheme["seats"]})
        self.assertEqual({seat["ring"] for seat in scheme["seats"]}, {False})
        self.assertEqual({seat["colour"] for seat in scheme["seats"]}, {""})
        self.assertEqual([seat["number"] for seat in scheme["seats"] if seat["kind"] == "couple"], ["4", "5"])
        flagged = [seat for seat in scheme["seats"] if seat["mark"] == "flagged"]
        self.assertEqual([(seat["number"], seat["r"]) for seat in flagged], [("10", "13.75")])
        self.assertEqual([badge["letter"] for badge in scheme["badges"]], ["G", "L"])

    def test_modifiers_come_from_the_enumerations(self):
        for name in FIXTURES:
            for scheme in fixture_objects(name):
                with self.subTest(fixture=name, hidden=scheme["hidden"]):
                    self.assertLessEqual({seat["kind"] for seat in scheme["seats"]}, set(_table.KINDS))
                    self.assertLessEqual({seat["mark"] for seat in scheme["seats"]}, set(_table.MARKS))
                    self.assertLessEqual({seat["colour"] for seat in scheme["seats"]},
                                         {"", *_table.SEAT_COLOURS})
                    self.assertLessEqual({lab["anchor"] for lab in scheme["labels"]}, set(_table.ANCHORS))

    def test_guest_object_has_no_dietary_data(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                guest_object, _ = fixture_objects(name)
                self.assertEqual(guest_object["badges"], [])
                self.assertNotIn("flagged", json.dumps(guest_object))
                self.assertFalse(guest_object["hidden"])

    def test_guest_function_takes_no_letters_and_no_couple(self):
        parameters = inspect.signature(guest_scheme).parameters
        self.assertNotIn("letters", parameters)
        self.assertEqual(list(parameters), ["table", "own_seats", "plan_text", "label_width"])
        for name in list(parameters)[1:]:
            self.assertIs(parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        with self.assertRaises(TypeError):
            guest_scheme(l_table(), own_seats=[8], plan_text="8", letters={8: ["A"]})
        with self.assertRaises(TypeError):
            guest_scheme(l_table(), own_seats=[8], plan_text="8", **couple())
        self.assertEqual(
            list(inspect.signature(staff_scheme).parameters),
            ["table", "couple_seats", "couple_label", "couple_arm", "letters"],
        )

    def test_numbers_are_strings_of_half_or_quarter_pixels(self):
        for name in FIXTURES:
            for scheme in fixture_objects(name):
                for key, value in walk(scheme):
                    if key in NUMBER_KEYS:
                        with self.subTest(fixture=name, key=key, value=value):
                            self.assertIsInstance(value, str)
                            self.assertRegex(value, rf"\A{NUMBER_RE.pattern}\Z")
                for token in re.findall(r"[^MLAZ ]+", scheme["outline"]):
                    self.assertRegex(token, rf"\A{NUMBER_RE.pattern}\Z")

    def test_digest_of_the_objects_is_fixed(self):
        objects = [fixture_objects(name) for name in FIXTURES]
        text = json.dumps(objects, sort_keys=True)
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), DIGEST)

    def test_radii_follow_the_strokes(self):
        half = Fraction(1, 2)
        self.assertEqual(Fraction(_table.SEAT_R), _table.SEAT_DIAMETER * half - Fraction(_table.SEAT_STROKE) * half)
        self.assertEqual(Fraction(_table.FLAG_R), _table.SEAT_DIAMETER * half - Fraction(_table.FLAG_STROKE) * half)
        self.assertEqual(Fraction(_table.YOU_R), _table.YOU_DIAMETER * half - Fraction(_table.SEAT_STROKE) * half)
        self.assertEqual(_table.RING_R, "21")
        self.assertEqual(_table.BADGE_R, "9")


class InputTest(unittest.TestCase):
    def test_layout_functions_refuse_an_unchecked_table(self):
        table = changed(l_table, set_item(["seats", 1, "count"], 7))()
        expected = check_table(table).errors
        calls = (
            lambda: expand_seats(table),
            lambda: badge_capacity(table, 1),
            lambda: guest(table, [1]),
            lambda: staff(table, {}),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(TableError) as caught:
                    call()
                self.assertEqual(caught.exception.errors, expected)
        self.assertTrue(issubclass(TableError, ValueError))

    def test_layout_functions_refuse_contradictory_parameters(self):
        cases = (
            lambda: badge_capacity(l_table(), 17),
            lambda: badge_capacity(l_table(), True),
            lambda: guest(l_table(), []),
            lambda: guest(l_table(), [8, 8]),
            lambda: guest(l_table(), [17]),
            lambda: guest(l_table(), [8, 9, 10, 11]),
            lambda: guest(l_table(), [8], text=None),
            lambda: staff(l_table(), {}, pair=couple((4, 5, 6))),
            lambda: staff(l_table(), {}, pair=couple(arm="middle")),
            lambda: staff(l_table(), {}, pair=couple((), arm=None)),
            lambda: staff(l_table(), {}, pair=couple(label="")),
            lambda: staff(l_table(), {0: ["A"]}),
            lambda: staff(l_table(), {8: "A"}),
            lambda: staff(l_table(), {8: [""]}),
            lambda: staff(l_table(), [8]),
        )
        for number, call in enumerate(cases):
            with self.subTest(case=number):
                with self.assertRaises(TableError):
                    call()


# --------------------------------------------------------------------------
# The module itself
# --------------------------------------------------------------------------


class ModuleTest(unittest.TestCase):
    def test_module_computes_with_integers_and_the_standard_library_only(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                self.assertNotIsInstance(node.value, float, f"line {node.lineno}")
            if isinstance(node, (ast.BinOp, ast.AugAssign)):
                self.assertNotIsInstance(node.op, ast.Div, f"line {node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"float", "round"}, f"line {node.lineno}")
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported, {"re", "collections.abc", "typing"})


if __name__ == "__main__":
    unittest.main()
