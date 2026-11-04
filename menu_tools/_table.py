"""The table plan: checks of a table description, seat layout, outline, labels.

A table is a set of rectangular arms in a field (the user units of the SVG
`viewBox`; 318 x 310 unless `width` and `height` give another size) and an
ordered list of seats, each on one side of an arm::

    {"label": "L-shaped table",
     "arms": [{"id": "top", "x": 40, "y": 60, "width": 200, "height": 52},
              {"id": "right", "x": 188, "y": 60, "width": 52, "height": 200}],
     "seats": [{"arm": "top", "side": "left"},
               {"arm": "top", "side": "top", "count": 5}, ...]}

The number of a seat is its position in the expanded list of seats (`count`
repeats an item).  The seats of a side are spread evenly and centred on the
free part of the side, clockwise; `arms[].shift` moves the group of a side
along it.  `seats[].align` lines seats up with other seats: an element per
seat of the item, the number of another seat or null; such a seat takes the
coordinate of that seat along its own side (x on the top and the bottom, y
on the left and the right), and the other seats of its side are laid out
around it (see `_place`).  The couple (their seats, label and arm) is a
separate part of the menu data and comes in as parameters.

Every coordinate is computed in whole half pixels (ints) and every number of
the output is a string ("66", "66.5"), so the result does not depend on the
platform or the Python version.  Standard library only, no input or output;
the markup is the business of the template fragment.

Public functions: `check_table`, `check_couple`, `expand_seats`,
`badge_capacity`, `guest_scheme`, `staff_scheme`.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, NamedTuple

# --------------------------------------------------------------------------
# Constants (px, the user units of the viewBox)
# --------------------------------------------------------------------------

#: The field of the plan when the table gives no size of its own.
FIELD_WIDTH = 318
FIELD_HEIGHT = 310
#: The limits of `table.width` and `table.height`.  The drawing is scaled
#: down to the width of its card, type and all: on the narrowest phone (320
#: px) the card gives it about 280 px, so a field of 480 is drawn at about
#: 0.6 of its size and the 12 px type of the plan at about 7 px, still
#: legible; a wider field would make it smaller.  The height does not change
#: the scale: up to 640, two default fields, the plan stays within a screen
#: or two.  The lower limits are about three quarters and half of the
#: default size: an arm with a row of seats on each side fits, and smaller
#: numbers are more likely a typo than a table.
MIN_FIELD_WIDTH = 240
MAX_FIELD_WIDTH = 480
MIN_FIELD_HEIGHT = 160
MAX_FIELD_HEIGHT = 640

#: Seat centre to the edge of its arm.
SEAT_CLEARANCE = 22
#: Seat centre to the next seat centre on a side.
SEAT_PITCH = 42
#: The tightest pitch on a side: a seat and a gap of 4 px.
SEAT_PITCH_MIN = 34
SEAT_DIAMETER = 30
#: The circle of a seat of the guest.
YOU_DIAMETER = 34
#: The ring around a seat of the guest.
RING_WIDTH = 4
RING_RADIUS = YOU_DIAMETER // 2 + RING_WIDTH
#: The least gap between the circle of a guest seat and any arm.
ARM_GAP = 2
#: The radius of the convex corners of the outline.
ARM_RADIUS = 10
MIN_ARM_SIZE = 2 * ARM_RADIUS

BADGE_RADIUS = 9
#: Seat centre to a badge centre, along x and along y.
BADGE_OFFSET = 12
MAX_BADGES = 4

#: Seat centre to the near edge of the "You" label: the edge of the ring.
LABEL_GAP = RING_RADIUS
#: The box kept for a label (12 px bold: "You" is about 23 px wide).
LABEL_WIDTH = 26
LABEL_HEIGHT = 14
#: How far a label keeps from the centre of another seat.
SEAT_KEEP_OUT = SEAT_DIAMETER // 2 + 2

#: The colours of the seats of a guest record, in the order of its seats:
#: the modifier `seat--colour-<n>` of a seat of the guest on the plan (and
#: of its name under the plan), drawn in the token `--color-seat-<n>`.  A
#: record has at most this many seats.
SEAT_COLOURS = ("1", "2", "3")

#: Estimated width of a capital of the couple label, half px (7.5 px at
#: 11 px with 0.06em tracking): there is no text measuring at build time.
COUPLE_CHAR_HALVES = 15
#: The couple label keeps this far from the ends of the free part of its arm.
COUPLE_PADDING = 4

MAX_SHIFT = SEAT_PITCH
MAX_COUNT = 20
#: A three-digit number does not fit into a seat.
MAX_SEATS = 99

#: Stroke of a seat, px; tied to the --line-width-seat token.
SEAT_STROKE = "1.5"
#: Stroke of a seat with a dietary note, px; tied to the --line-width-flag token.
FLAG_STROKE = "2.5"
# The radii of the circles: the outer edge of the centred stroke lies on the
# diameter (radius = diameter halved minus half the stroke).  Exact binary
# fractions, written out so that the text never depends on the platform.
SEAT_R = "14.25"   # SEAT_DIAMETER and SEAT_STROKE
FLAG_R = "13.75"   # SEAT_DIAMETER and FLAG_STROKE
YOU_R = "16.25"    # YOU_DIAMETER and SEAT_STROKE
RING_R = str(RING_RADIUS)
BADGE_R = str(BADGE_RADIUS)

SIDES = ("top", "right", "bottom", "left")
KINDS = ("regular", "couple", "you")
MARKS = ("none", "flagged")
ANCHORS = ("start", "end", "middle")

_TABLE_FIELDS = ("arms", "height", "label", "seats", "width")
_ARM_FIELDS = ("height", "id", "shift", "width", "x", "y")
_SEAT_FIELDS = ("align", "arm", "count", "side")
_ID_RE = re.compile(r"[a-z][a-z0-9-]{0,39}")
_ID_RULE = "an id: a-z, 0-9 and '-', starting with a letter, at most 40 characters"
_OUTWARD = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}
# Badge spots in the order they are taken: top right (as in the mockup), top
# left, bottom right, bottom left.
_BADGE_SPOTS = (
    (BADGE_OFFSET, -BADGE_OFFSET),
    (-BADGE_OFFSET, -BADGE_OFFSET),
    (BADGE_OFFSET, BADGE_OFFSET),
    (-BADGE_OFFSET, BADGE_OFFSET),
)


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------


class TableError(ValueError):
    """An unchecked or contradictory input of a layout function."""

    def __init__(self, errors: Sequence[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


class TableCheck(NamedTuple):
    """The result of a check: messages and the number of seats (or None)."""

    errors: list[str]
    warnings: list[str]
    total: int | None


class _Arm(NamedTuple):
    index: int
    id: str
    x0: int
    y0: int
    x1: int
    y1: int
    shift: dict


class _Seat(NamedTuple):
    number: int
    item: int  # position of its item in table.seats
    arm: _Arm
    side: str
    cx: int  # half px
    cy: int  # half px


class _Field(NamedTuple):
    """The size of the field, px."""

    width: int
    height: int


class _Parsed(NamedTuple):
    label: str
    field: _Field
    arms: list
    ids: dict  # id -> position of the arm
    specs: list  # (arm id, side, item) per seat number
    total: int | None
    targets: list  # the seat each seat aligns to (or None), per seat number


class _Plan(NamedTuple):
    label: str
    field: _Field
    arms: list
    ids: dict
    seats: list
    outline: str


#: A box in half px: x0, y0, x1, y1.
_Box = tuple[int, int, int, int]
#: A label spot: its box, the text position (half px) and the text anchor.
_Spot = tuple[_Box, int, int, str]


class _Caption(NamedTuple):
    text: str
    x: int  # half px
    y: int  # half px
    vertical: bool
    fits: bool


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _px(half: int) -> str:
    """Half pixels as text: 132 -> "66", 133 -> "66.5", -5 -> "-2.5"."""
    sign = "-" if half < 0 else ""
    whole, rest = divmod(abs(half), 2)
    return f"{sign}{whole}.5" if rest else f"{sign}{whole}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _one_line(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != "" and value.splitlines() == [value]


def _numbers_text(numbers: Sequence[int]) -> str:
    """`[2, 3, 4, 5, 6, 17, 18]` -> "seats 2-6, 17, 18"; `[11]` -> "seat 11"."""
    if len(numbers) == 1:
        return f"seat {numbers[0]}"
    runs: list[list[int]] = []
    for number in numbers:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    parts = []
    for run in runs:
        if len(run) > 2:
            parts.append(f"{run[0]}-{run[-1]}")
        else:
            parts.extend(str(number) for number in run)
    return "seats " + ", ".join(parts)


def _item_text(first: int, count: int | None) -> str:
    if count is None:
        return f"seats from {first}"
    return _numbers_text(range(first, first + count))


def _seat_where(seat: _Seat) -> str:
    return f"table.seats[{seat.item}] (seat {seat.number})"


def _align_where(specs: Sequence[tuple], number: int) -> str:
    """The element of `align` that belongs to a seat: its item and position."""
    item = specs[number - 1][2]
    first = next(n for n, spec in enumerate(specs, 1) if spec[2] == item)
    return f"table.seats[{item}].align[{number - first}] (seat {number})"


def _seat_numbers(value: Any) -> list | None:
    """A list of ints from a sequence of ints, or None."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    numbers = list(value)
    return numbers if all(_is_int(number) for number in numbers) else None


# --------------------------------------------------------------------------
# Parsing (structure rules)
# --------------------------------------------------------------------------


def _parse(table: Any, errors: list[str]) -> _Parsed | None:
    if not isinstance(table, dict):
        errors.append("table: expected an object")
        return None
    if any(key not in _TABLE_FIELDS for key in table):
        errors.append(f"table: unknown field (allowed: {', '.join(_TABLE_FIELDS)})")
    label = table.get("label")
    if not _one_line(label):
        errors.append("table.label: expected a non-empty one-line string")
    field = _parse_field(table, errors)
    arms, ids = _parse_arms(table.get("arms"), field, errors)
    specs, total, targets = _parse_seats(table.get("seats"), ids, errors)
    if total is not None:
        errors.extend(_check_targets(specs, targets, total, ids))
    field = field or _Field(FIELD_WIDTH, FIELD_HEIGHT)  # only errors follow a wrong size
    return _Parsed(label, field, arms, ids, specs, total, targets)


def _parse_field(table: dict, errors: list[str]) -> _Field | None:
    """The size of the field (the default one when the table gives none);
    None when a size is wrong."""
    size = {}
    for key, default, low, high in (("width", FIELD_WIDTH, MIN_FIELD_WIDTH, MAX_FIELD_WIDTH),
                                    ("height", FIELD_HEIGHT, MIN_FIELD_HEIGHT, MAX_FIELD_HEIGHT)):
        value = table.get(key, default)
        if not _is_int(value) or not low <= value <= high:
            errors.append(f"table.{key}: expected an integer from {low} to {high} (px)")
        else:
            size[key] = value
    return _Field(size["width"], size["height"]) if len(size) == 2 else None


def _parse_arms(raw: Any, field: _Field | None, errors: list[str]) -> tuple[list, dict]:
    arms: list[_Arm] = []
    ids: dict[str, int] = {}
    if not isinstance(raw, list) or not raw:
        errors.append("table.arms: expected a non-empty array")
        return arms, ids
    for index, item in enumerate(raw):
        where = f"table.arms[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: expected an object")
            continue
        if any(key not in _ARM_FIELDS for key in item):
            errors.append(f"{where}: unknown field (allowed: {', '.join(_ARM_FIELDS)})")
        good = True
        arm_id = item.get("id")
        if not isinstance(arm_id, str) or not _ID_RE.fullmatch(arm_id):
            errors.append(f"{where}.id: expected {_ID_RULE}")
            good = False
        elif arm_id in ids:
            errors.append(f"{where}.id: repeats table.arms[{ids[arm_id]}].id")
            good = False
        else:
            ids[arm_id] = index
        size: dict[str, int] = {}
        for key in ("x", "y", "width", "height"):
            value = item.get(key)
            if not _is_int(value):
                errors.append(f"{where}.{key}: expected an integer (px)")
            elif key in ("width", "height") and value < MIN_ARM_SIZE:
                errors.append(f"{where}.{key}: expected at least {MIN_ARM_SIZE} px")
            else:
                size[key] = value
        shift = _parse_shift(item, where, errors)
        if len(size) < 4 or shift is None:
            continue
        x0, y0 = size["x"], size["y"]
        x1, y1 = x0 + size["width"], y0 + size["height"]
        if field is not None and (x0 < 0 or y0 < 0 or x1 > field.width or y1 > field.height):
            errors.append(f"{where}: lies outside the {field.width}x{field.height} field")
            continue
        if good:
            arms.append(_Arm(index, arm_id, x0, y0, x1, y1, shift))
    return arms, ids


def _parse_shift(item: dict, where: str, errors: list[str]) -> dict | None:
    if "shift" not in item:
        return {}
    shift = item["shift"]
    if not isinstance(shift, dict):
        errors.append(f"{where}.shift: expected an object with sides as keys")
        return None
    good = True
    if any(key not in SIDES for key in shift):
        errors.append(f"{where}.shift: unknown side (allowed: {', '.join(SIDES)})")
        good = False
    for side in SIDES:
        if side in shift:
            value = shift[side]
            if not _is_int(value) or not -MAX_SHIFT <= value <= MAX_SHIFT:
                errors.append(
                    f"{where}.shift.{side}: expected an integer from -{MAX_SHIFT} to {MAX_SHIFT}"
                )
                good = False
    return {side: shift[side] for side in SIDES if side in shift} if good else None


def _parse_seats(raw: Any, ids: dict, errors: list[str]) -> tuple[list, int | None, list]:
    specs: list[tuple[Any, Any, int]] = []
    targets: list[int | None] = []
    if not isinstance(raw, list) or not raw:
        errors.append("table.seats: expected a non-empty array")
        return specs, None, targets
    number = 1
    known = True
    for index, item in enumerate(raw):
        where = f"table.seats[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} ({_item_text(number, 1)}): expected an object")
            known = False
            number += 1
            continue
        count: int | None = 1
        if "count" in item:
            value = item["count"]
            count = value if _is_int(value) and 1 <= value <= MAX_COUNT else None
        seats = _item_text(number, count)
        if any(key not in _SEAT_FIELDS for key in item):
            errors.append(f"{where} ({seats}): unknown field (allowed: {', '.join(_SEAT_FIELDS)})")
        if count is None:
            errors.append(f"{where}.count ({seats}): expected an integer from 1 to {MAX_COUNT}")
            known = False
        arm_id, side = item.get("arm"), item.get("side")
        if not isinstance(arm_id, str) or arm_id not in ids:
            errors.append(f"{where}.arm ({seats}): not an id of table.arms")
        if not isinstance(side, str) or side not in SIDES:
            errors.append(f"{where}.side ({seats}): expected one of {', '.join(SIDES)}")
        targets.extend(_parse_align(item, where, number, count, errors))
        count = count or 1
        specs.extend((arm_id, side, index) for _ in range(count))
        number += count
    if number - 1 > MAX_SEATS:
        errors.append(f"table.seats: at most {MAX_SEATS} seats")
    return specs, (number - 1 if known else None), targets


def _parse_align(item: dict, where: str, first: int, count: int | None, errors: list[str]) -> list:
    """The seats that the seats of an item align to (None: not aligned), one
    per seat; `count` is None when the count of the item is wrong."""
    targets: list[int | None] = [None] * (count or 1)
    if "align" not in item:
        return targets
    value = item["align"]
    where = f"{where}.align"
    if count is None:
        if not isinstance(value, list):
            errors.append(f"{where} ({_item_text(first, None)}): expected an array: "
                          "a seat number or null for each seat")
        return targets
    if not isinstance(value, list) or len(value) != count:
        wanted = "one element: a seat number or null" if count == 1 else (
            f"{count} elements: a seat number or null for each seat"
        )
        errors.append(f"{where} ({_item_text(first, count)}): expected an array of {wanted}")
        return targets
    for j, element in enumerate(value):
        if element is None:
            continue
        if _is_int(element) and element >= 1:
            targets[j] = element
        else:
            errors.append(f"{where}[{j}] (seat {first + j}): expected a seat number or null")
    return targets


def _check_targets(specs: Sequence[tuple], targets: Sequence, total: int, ids: dict) -> list[str]:
    """The seats that seats align to: seats of the table, of another side."""
    errors = []
    for number, target in enumerate(targets, 1):
        if target is None:
            continue
        where = _align_where(specs, number)
        if target > total:
            errors.append(f"{where}: refers to no seat: the table has {total} seats")
        elif target == number:
            errors.append(f"{where}: refers to the seat itself")
        else:
            arm_id, side, _item = specs[number - 1]
            if (
                isinstance(arm_id, str) and arm_id in ids and side in SIDES
                and specs[target - 1][:2] == (arm_id, side)
            ):
                errors.append(f"{where}: refers to seat {target} on the same side of the same arm")
    return errors


# --------------------------------------------------------------------------
# Sides and seat layout
# --------------------------------------------------------------------------


def _side_span(arm: _Arm, side: str) -> tuple[int, int]:
    """The side as an interval of its axis: x for top and bottom, y otherwise."""
    return (arm.x0, arm.x1) if side in ("top", "bottom") else (arm.y0, arm.y1)


def _centre_line(arm: _Arm, side: str) -> int:
    """The other coordinate of the seat centres of a side, px."""
    if side == "top":
        return arm.y0 - SEAT_CLEARANCE
    if side == "right":
        return arm.x1 + SEAT_CLEARANCE
    if side == "bottom":
        return arm.y1 + SEAT_CLEARANCE
    return arm.x0 - SEAT_CLEARANCE


def _cover(other: _Arm, arm: _Arm, side: str) -> tuple[int, int] | None:
    """The projection of `other` on a side of `arm` when it covers the outside of the side."""
    if side == "top" and other.y0 < arm.y0 <= other.y1:
        return other.x0, other.x1
    if side == "bottom" and other.y0 <= arm.y1 < other.y1:
        return other.x0, other.x1
    if side == "left" and other.x0 < arm.x0 <= other.x1:
        return other.y0, other.y1
    if side == "right" and other.x0 <= arm.x1 < other.x1:
        return other.y0, other.y1
    return None


def _free_parts(arm: _Arm, side: str, arms: Sequence[_Arm]) -> list[tuple[int, int]]:
    """The free parts of a side; an end cut by another arm steps back by SEAT_CLEARANCE."""
    low, high = _side_span(arm, side)
    parts = [(low, high, False, False)]  # start, end, start is cut, end is cut
    for other in arms:
        if other.index == arm.index:
            continue
        cover = _cover(other, arm, side)
        if cover is None:
            continue
        c0, c1 = cover
        kept = []
        for a, b, cut_a, cut_b in parts:
            if c1 <= a or c0 >= b:
                kept.append((a, b, cut_a, cut_b))
                continue
            if c0 > a:
                kept.append((a, c0, cut_a, True))
            if c1 < b:
                kept.append((c1, b, True, cut_b))
        parts = kept
    result = []
    for a, b, cut_a, cut_b in parts:
        a += SEAT_CLEARANCE if cut_a else 0
        b -= SEAT_CLEARANCE if cut_b else 0
        if b > a:
            result.append((a, b))
    return result


def _groups(specs: Sequence[tuple]) -> dict:
    """(arm id, side) -> seat numbers, in the order of the first seat."""
    groups: dict[tuple[str, str], list[int]] = {}
    for number, (arm_id, side, _item) in enumerate(specs, 1):
        groups.setdefault((arm_id, side), []).append(number)
    return groups


def _pitch(count: int, free: int) -> int:
    """The pitch of `count` seats on a free length, half px: 42, else squeezed."""
    if count == 1:
        return 2 * SEAT_PITCH
    # the outer seats stay within the free part (the check keeps it >= 34)
    return min(2 * SEAT_PITCH, (2 * free - 2 * SEAT_DIAMETER) // (count - 1))


def _clockwise(side: str) -> int:
    """1 where the seats go clockwise along the axis (top, right), else -1."""
    return 1 if side in ("top", "right") else -1


def _align_links(specs: Sequence[tuple], targets: Sequence) -> dict:
    """Seat -> the seats its place depends on: an aligned seat depends on the
    seat it aligns to, another seat of a side with aligned seats on the
    aligned seats next to it on the side (one or two)."""
    links: dict[int, list[int]] = {}
    for numbers in _groups(specs).values():
        anchors = [k for k, number in enumerate(numbers) if targets[number - 1] is not None]
        for k, number in enumerate(numbers):
            if targets[number - 1] is not None:
                links[number] = [targets[number - 1]]
            else:
                before = [numbers[i] for i in anchors if i < k][-1:]
                after = [numbers[i] for i in anchors if i > k][:1]
                links[number] = before + after
    return links


def _align_order(specs: Sequence[tuple], targets: Sequence) -> tuple[list, list]:
    """The seats in an order in which every seat comes after the seats its
    place depends on, and the circles of these links (lists of seats)."""
    links = _align_links(specs, targets)
    order: list[int] = []
    circles: list[list[int]] = []
    done: dict[int, bool] = {}  # False while the seat is on the current path
    for start in range(1, len(specs) + 1):
        if start in done:
            continue
        done[start] = False
        path, stack = [start], [iter(links[start])]
        while stack:
            following = next(stack[-1], None)
            if following is None:
                stack.pop()
                number = path.pop()
                done[number] = True
                order.append(number)
            elif following not in done:
                done[following] = False
                path.append(following)
                stack.append(iter(links[following]))
            elif not done[following]:
                circles.append(path[path.index(following):])
    return order, circles


def _check_circles(specs: Sequence[tuple], targets: Sequence) -> list[str]:
    """Seats that align to each other in a circle (through the other seats of
    a side, which follow its aligned seats)."""
    errors = []
    seen = set()
    for circle in _align_order(specs, targets)[1]:
        numbers = sorted(circle)
        if tuple(numbers) in seen:
            continue
        seen.add(tuple(numbers))
        first = min(number for number in circle if targets[number - 1] is not None)
        errors.append(
            f"{_align_where(specs, first)}: the alignment goes round in a circle "
            f"through {_numbers_text(numbers)}"
        )
    return errors


def _place(specs: Sequence[tuple], arms: Sequence[_Arm], targets: Sequence) -> list[_Seat]:
    """The seat centres.

    The seats of a side without aligned seats are spread evenly and centred
    on its free part, at the pitch of 42 px or squeezed so that the outer
    seats keep 15 px (a seat radius) from its ends, and moved by the shift of
    the side.  On a side with aligned seats each of them takes the coordinate
    of the seat it aligns to along the side; the seats between two aligned
    seats are spread evenly between them; those before the first and after
    the last one follow it at the pitch of 42 px outwards or, when they would
    come closer than 15 px to the end of the free part, are spread evenly
    between that point and the aligned seat.  The shift of such a side has no
    effect.  The circles of alignments are checked before.
    """
    by_id = {arm.id: arm for arm in arms}
    along: dict[int, int] = {}  # seat -> its centre along its side, half px
    lines: dict[int, int] = {}  # seat -> the centre line of its side, half px
    aligned: dict[int, tuple] = {}  # seat -> its side with aligned seats
    for (arm_id, side), numbers in _groups(specs).items():
        arm = by_id[arm_id]
        (a, b), = _free_parts(arm, side, arms)
        for number in numbers:
            lines[number] = 2 * _centre_line(arm, side)
        anchors = [k for k, number in enumerate(numbers) if targets[number - 1] is not None]
        if anchors:
            for number in numbers:
                aligned[number] = (numbers, anchors, side, a, b)
            continue
        count = len(numbers)
        pitch = _pitch(count, b - a)
        start = (2 * (a + b) - (count - 1) * pitch) // 2 + 2 * arm.shift.get(side, 0)
        for k, number in enumerate(numbers):
            # clockwise: top left to right, right downwards, bottom right to
            # left, left upwards
            slot = k if side in ("top", "right") else count - 1 - k
            along[number] = start + slot * pitch

    def centre(number: int) -> tuple[int, int]:
        if specs[number - 1][1] in ("top", "bottom"):
            return along[number], lines[number]
        return lines[number], along[number]

    for number in _align_order(specs, targets)[0]:
        if number in along:
            continue
        target = targets[number - 1]
        if target is None:
            along.update(_spread(number, aligned[number], along))
        else:
            cx, cy = centre(target)
            along[number] = cx if specs[number - 1][1] in ("top", "bottom") else cy
    return [
        _Seat(number, item, by_id[arm_id], side, *centre(number))
        for number, (arm_id, side, item) in enumerate(specs, 1)
    ]


def _spread(number: int, side_info: tuple, along: dict) -> dict:
    """The places (half px along the side) of the seats without alignment
    next to `number` on a side with aligned seats, between two aligned seats
    or before the first or after the last one."""
    numbers, anchors, side, a, b = side_info
    sign = _clockwise(side)
    # clockwise coordinates: the seats of the side come in increasing order
    low, high = sorted((sign * 2 * a, sign * 2 * b))
    low, high = low + SEAT_DIAMETER, high - SEAT_DIAMETER  # 15 px from the ends
    k = numbers.index(number)
    before = [i for i in anchors if i < k][-1:]
    after = [i for i in anchors if i > k][:1]
    # only these aligned seats are placed already
    place = {i: sign * along[numbers[i]] for i in before + after}
    pitch = 2 * SEAT_PITCH
    if before and after:
        p, q = before[0], after[0]
        span = place[q] - place[p]
        run = {i: place[p] + (i - p) * span // (q - p) for i in range(p + 1, q)}
    elif after:
        q = after[0]
        if place[q] - q * pitch < low:
            pitch = max(0, (place[q] - low) // q)
        run = {i: place[q] - (q - i) * pitch for i in range(q)}
    else:
        p = before[0]
        rest = len(numbers) - 1 - p
        if place[p] + rest * pitch > high:
            pitch = max(0, (high - place[p]) // rest)
        run = {i: place[p] + (i - p) * pitch for i in range(p + 1, len(numbers))}
    return {numbers[i]: sign * value for i, value in run.items()}


def _distance2_to_box(cx: int, cy: int, box: _Box) -> int:
    """The squared distance from a point to a box (all in the same units)."""
    x0, y0, x1, y1 = box
    dx = max(x0 - cx, 0, cx - x1)
    dy = max(y0 - cy, 0, cy - y1)
    return dx * dx + dy * dy


def _arm_box(arm: _Arm) -> _Box:
    """The arm in half px."""
    return 2 * arm.x0, 2 * arm.y0, 2 * arm.x1, 2 * arm.y1


# --------------------------------------------------------------------------
# Outline of the union of the arms
# --------------------------------------------------------------------------


def _outline_edges(arms: Sequence[_Arm]) -> dict:
    """Boundary edges of the union, each with the inside on its right (screen
    coordinates): start point -> end points."""
    xs = sorted({value for arm in arms for value in (arm.x0, arm.x1)})
    ys = sorted({value for arm in arms for value in (arm.y0, arm.y1)})
    covered = set()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            if any(
                arm.x0 <= xs[i] and xs[i + 1] <= arm.x1 and arm.y0 <= ys[j] and ys[j + 1] <= arm.y1
                for arm in arms
            ):
                covered.add((i, j))
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for i, j in sorted(covered):
        x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]
        if (i, j - 1) not in covered:
            edges.setdefault((x0, y0), []).append((x1, y0))
        if (i + 1, j) not in covered:
            edges.setdefault((x1, y0), []).append((x1, y1))
        if (i, j + 1) not in covered:
            edges.setdefault((x1, y1), []).append((x0, y1))
        if (i - 1, j) not in covered:
            edges.setdefault((x0, y1), []).append((x0, y0))
    return edges


def _corner_touches(arms: Sequence[_Arm]) -> list[str]:
    """Messages about arms that meet only at a corner (the outline pinches)."""
    messages = []
    for point, ends in sorted(_outline_edges(arms).items()):
        if len(ends) > 1:
            corners = sorted(
                arm.index
                for arm in arms
                if point[0] in (arm.x0, arm.x1) and point[1] in (arm.y0, arm.y1)
            )
            names = " and ".join(f"table.arms[{index}]" for index in corners)
            messages.append(f"{names}: touch only at a corner")
    return messages


def _outline_loops(arms: Sequence[_Arm]) -> list[list[tuple[int, int]]]:
    """Closed clockwise loops of the union, without collinear points."""
    left = {point: ends[0] for point, ends in _outline_edges(arms).items()}
    loops = []
    while left:
        start = min(left)
        loop = [start]
        point = left.pop(start)
        while point != start:
            loop.append(point)
            point = left.pop(point)
        size = len(loop)
        clean = []
        for k in range(size):
            a, b, c = loop[k - 1], loop[k], loop[(k + 1) % size]
            if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) != 0:
                clean.append(b)
        loops.append(clean)
    return loops


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _outline(arms: Sequence[_Arm]) -> str:
    """SVG path data of the union: convex corners rounded, concave ones sharp."""
    out = []
    for loop in _outline_loops(arms):
        size = len(loop)
        pieces = []
        for k in range(size):
            p, v, q = loop[k - 1], loop[k], loop[(k + 1) % size]
            din = (_sign(v[0] - p[0]), _sign(v[1] - p[1]))
            dout = (_sign(q[0] - v[0]), _sign(q[1] - v[1]))
            if din[0] * dout[1] - din[1] * dout[0] > 0:  # a right turn: convex
                length_in = abs(v[0] - p[0]) + abs(v[1] - p[1])
                length_out = abs(q[0] - v[0]) + abs(q[1] - v[1])
                # half px: the radius is at most half of either edge
                r = min(2 * ARM_RADIUS, length_in, length_out)
                a = (2 * v[0] - din[0] * r, 2 * v[1] - din[1] * r)
                b = (2 * v[0] + dout[0] * r, 2 * v[1] + dout[1] * r)
                pieces.append((a, f"A{_px(r)} {_px(r)} 0 0 1 {_px(b[0])} {_px(b[1])}", b))
            else:
                corner = (2 * v[0], 2 * v[1])
                pieces.append((corner, "", corner))
        start = pieces[0][2]
        d = [f"M{_px(start[0])} {_px(start[1])}"]
        for a, arc, _b in pieces[1:] + pieces[:1]:
            d.append(f"L{_px(a[0])} {_px(a[1])}")
            d.append(arc)
        d.append("Z")
        out.append("".join(d))
    return "".join(out)


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------


def check_table(table: Any) -> TableCheck:
    """Check a table description (parsed JSON of any type).

    The messages name positions in `table` and seat numbers, never ids,
    labels or other values of the data; they carry no file prefix.  `total`
    is the number of seats when the list of seats could be read, else None.
    """
    check, _plan = _check(table)
    return check


def _check(table: Any) -> tuple[TableCheck, _Plan | None]:
    """The rules in waves: structure, circles of alignments, arms, sides,
    aligned seats, seats, labels; a wave runs only when the ones before it
    found no error."""
    errors: list[str] = []
    warnings: list[str] = []
    parsed = _parse(table, errors)
    total = parsed.total if parsed else None
    if errors:
        return TableCheck(errors, warnings, total), None
    arms, specs, targets = parsed.arms, parsed.specs, parsed.targets
    errors = _check_circles(specs, targets)
    if not errors:
        errors = _check_arms(arms)
    if not errors:
        errors = _check_sides(specs, arms, targets, warnings)
    if errors:
        return TableCheck(errors, warnings, total), None
    seats = _place(specs, arms, targets)
    errors = _check_aligned(seats, specs, arms, targets, warnings)
    if not errors:
        errors = _check_seats(seats, arms, parsed.field)
    if errors:
        return TableCheck(errors, warnings, total), None

    plan = _Plan(parsed.label, parsed.field, arms, parsed.ids, seats, _outline(arms))
    # Any seat can be the one seat of a guest, so every seat needs room for
    # "You".  With the constants above the label of a seat always fits onto
    # its own arm; the check guards the layout against a change of the
    # constants.
    for seat in seats:
        if _label_spot(seat, plan) is None:
            errors.append(f"{_seat_where(seat)}: no room for the 'You' label")
    return TableCheck(errors, warnings, total), (None if errors else plan)


def _check_arms(arms: Sequence[_Arm]) -> list[str]:
    """An arm inside another one; arms that meet only at a corner."""
    errors = []
    for a in arms:
        for b in arms:
            if a.index == b.index:
                continue
            inside = b.x0 <= a.x0 and a.x1 <= b.x1 and b.y0 <= a.y0 and a.y1 <= b.y1
            same = (a.x0, a.y0, a.x1, a.y1) == (b.x0, b.y0, b.x1, b.y1)
            if inside and (not same or a.index > b.index):
                errors.append(f"table.arms[{a.index}]: lies inside table.arms[{b.index}]")
    errors.extend(_corner_touches(arms))
    return errors


def _check_sides(
    specs: Sequence[tuple], arms: Sequence[_Arm], targets: Sequence, warnings: list[str]
) -> list[str]:
    """One free part per side, room for its seats; a squeezed pitch is a
    warning (on a side with aligned seats it is known only after the layout)."""
    errors = []
    by_id = {arm.id: arm for arm in arms}
    for (arm_id, side), numbers in _groups(specs).items():
        arm = by_id[arm_id]
        where = f"table.arms[{arm.index}] side '{side}'"
        listed = _numbers_text(numbers)
        parts = _free_parts(arm, side, arms)
        count = len(numbers)
        if not parts:
            errors.append(f"{where}: covered by another arm, no room for {listed}")
        elif len(parts) > 1:
            errors.append(f"{where}: split in two by another arm; make two arms of it ({listed})")
        else:
            a, b = parts[0]
            need = (count - 1) * SEAT_PITCH_MIN + SEAT_DIAMETER
            if b - a < need:
                errors.append(
                    f"{where}: too short for {listed}: "
                    f"{count} seat(s) need {need} px of free length"
                )
            elif _pitch(count, b - a) < 2 * SEAT_PITCH and all(
                targets[number - 1] is None for number in numbers
            ):
                warnings.append(f"{where}: {listed} squeezed closer than {SEAT_PITCH} px")
    return errors


def _check_aligned(
    seats: Sequence[_Seat],
    specs: Sequence[tuple],
    arms: Sequence[_Arm],
    targets: Sequence,
    warnings: list[str],
) -> list[str]:
    """Each aligned seat on the free part of its side and in the clockwise
    order of the side; a squeezed pitch on such a side is a warning."""
    errors: list[str] = []
    squeezed: list[str] = []
    by_id = {arm.id: arm for arm in arms}
    for (arm_id, side), numbers in _groups(specs).items():
        anchors = [number for number in numbers if targets[number - 1] is not None]
        if not anchors:
            continue
        arm = by_id[arm_id]
        (a, b), = _free_parts(arm, side, arms)
        along = {
            number: seats[number - 1].cx if side in ("top", "bottom") else seats[number - 1].cy
            for number in numbers
        }
        # clockwise coordinates: the seats of the side come in increasing order
        place = {number: _clockwise(side) * along[number] for number in numbers}
        inside = []
        for number in anchors:
            if 2 * a <= along[number] <= 2 * b:
                inside.append(number)
            else:
                errors.append(
                    f"{_align_where(specs, number)}: lines the seat up off the free part of its side"
                )
        for previous, number in zip(inside, inside[1:]):
            if place[number] <= place[previous]:
                errors.append(
                    f"{_align_where(specs, number)}: puts the seat at or before seat {previous}, "
                    "against the clockwise order of its side"
                )
        gaps = [place[second] - place[first] for first, second in zip(numbers, numbers[1:])]
        if any(gap < 2 * SEAT_PITCH for gap in gaps):
            squeezed.append(
                f"table.arms[{arm.index}] side '{side}': {_numbers_text(numbers)} "
                f"squeezed closer than {SEAT_PITCH} px"
            )
    if not errors:
        warnings.extend(squeezed)
    return errors


def _check_seats(seats: Sequence[_Seat], arms: Sequence[_Arm], field: _Field) -> list[str]:
    """Each seat in the field, on its side, clear of the arms and of the other seats."""
    errors = []
    edge = YOU_DIAMETER  # half px: the radius of a guest seat
    reach = YOU_DIAMETER + 2 * ARM_GAP  # half px
    for seat in seats:
        where = _seat_where(seat)
        if not (
            edge <= seat.cx <= 2 * field.width - edge and edge <= seat.cy <= 2 * field.height - edge
        ):
            errors.append(f"{where}: does not fit into the {field.width}x{field.height} field")
        (a, b), = _free_parts(seat.arm, seat.side, arms)
        along = seat.cx if seat.side in ("top", "bottom") else seat.cy
        if not 2 * a <= along <= 2 * b:
            errors.append(f"{where}: the shift moves it off its side")
        if any(_distance2_to_box(seat.cx, seat.cy, _arm_box(arm)) < reach * reach for arm in arms):
            errors.append(f"{where}: touches an arm of the table")
    least = 2 * SEAT_PITCH_MIN
    for k, s in enumerate(seats):
        for t in seats[k + 1:]:
            if (s.cx - t.cx) ** 2 + (s.cy - t.cy) ** 2 < least * least:
                errors.append(f"seats {s.number} and {t.number}: closer than {SEAT_PITCH_MIN} px")
    return errors


def _checked(table: Any) -> _Plan:
    check, plan = _check(table)
    if plan is None:
        raise TableError(check.errors)
    return plan


# --------------------------------------------------------------------------
# The couple
# --------------------------------------------------------------------------


def check_couple(
    table: Any, seats: Sequence[int], label: str | None, arm: str | None
) -> TableCheck:
    """Check the couple against a table: their seats (from `couple.members`),
    the label (None: no label) and the arm of the label (None: the arm of the
    first seat).  The table itself is checked by `check_table`: when it has
    errors, only what does not depend on it is checked here.  The couple is
    drawn on the staff plan alone, where no seat has a "You" label: the
    couple label may lie anywhere on its arm.
    """
    errors: list[str] = []
    warnings: list[str] = []
    table_check, plan = _check(table)
    total = table_check.total
    numbers = _seat_numbers(seats)
    if (
        numbers is None
        or not 1 <= len(numbers) <= 2
        or len(set(numbers)) != len(numbers)
        or (total is not None and not all(1 <= number <= total for number in numbers))
    ):
        span = f" from 1 to {total}" if total is not None else ""
        errors.append(f"couple.members[].seat: expected 1-2 different seat numbers{span}")
    if label is not None and not _one_line(label):
        errors.append("couple.label: expected a non-empty one-line string")
    if arm is not None and plan is not None and (not isinstance(arm, str) or arm not in plan.ids):
        errors.append("couple.arm: not an id of table.arms")
    if errors or plan is None or label is None:
        return TableCheck(errors, warnings, total)
    if not _caption(plan, numbers, label, arm).fits:
        warnings.append("couple.label: may not fit inside the arm")
    return TableCheck(errors, warnings, total)


def _caption(plan: _Plan, couple_seats: Sequence[int], label: str, arm_id: str | None) -> _Caption:
    """The couple label: centred on the free part of its arm along the long axis."""
    if arm_id is None:
        arm = plan.seats[couple_seats[0] - 1].arm
    else:
        arm = next(a for a in plan.arms if a.id == arm_id)
    vertical = (arm.y1 - arm.y0) > (arm.x1 - arm.x0)
    low, high = (arm.y0, arm.y1) if vertical else (arm.x0, arm.x1)
    parts = [(low, high)]
    for other in plan.arms:
        if other.index == arm.index:
            continue
        # the part of the arm under another arm (the joint) is not free
        if other.x0 < arm.x1 and arm.x0 < other.x1 and other.y0 < arm.y1 and arm.y0 < other.y1:
            c0, c1 = (other.y0, other.y1) if vertical else (other.x0, other.x1)
            if c0 <= low and c1 >= high:
                continue
            kept = []
            for a, b in parts:
                if c1 <= a or c0 >= b:
                    kept.append((a, b))
                    continue
                if c0 > a:
                    kept.append((a, c0))
                if c1 < b:
                    kept.append((c1, b))
            parts = kept
    a, b = max(parts or [(low, high)], key=lambda part: (part[1] - part[0], -part[0]))
    text = label.upper()
    width = len(text) * COUPLE_CHAR_HALVES  # half px
    fits = width <= 2 * (b - a - 2 * COUPLE_PADDING)
    if vertical:
        x, y = arm.x0 + arm.x1, a + b
    else:
        x, y = a + b, arm.y0 + arm.y1
    return _Caption(text, x, y, vertical, fits)


# --------------------------------------------------------------------------
# Labels and badges
# --------------------------------------------------------------------------


def _overlap(a: _Box, b: _Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _label_candidates(seat: _Seat) -> Iterator[_Spot]:
    """(box, text x, text y, anchor) in half px: outwards from the table
    first, then right, left, up, down."""
    outward = _OUTWARD[seat.side]
    order = [outward] + [d for d in ((1, 0), (-1, 0), (0, -1), (0, 1)) if d != outward]
    g, w, h = 2 * LABEL_GAP, 2 * LABEL_WIDTH, 2 * LABEL_HEIGHT
    half_w, half_h = LABEL_WIDTH, LABEL_HEIGHT  # half of the box, in half px
    x, y = seat.cx, seat.cy
    for dx, dy in order:
        if dx == 1:
            yield (x + g, y - half_h, x + g + w, y + half_h), x + g, y, "start"
        elif dx == -1:
            yield (x - g - w, y - half_h, x - g, y + half_h), x - g, y, "end"
        elif dy == -1:
            yield (x - half_w, y - g - h, x + half_w, y - g), x, y - g - half_h, "middle"
        else:
            yield (x - half_w, y + g, x + half_w, y + g + h), x, y + g + half_h, "middle"


def _label_spot(seat: _Seat, plan: _Plan) -> _Spot | None:
    """The first spot of the "You" label inside the field that keeps off
    the other seats; the arms are avoided when possible (first pass), else
    the label may lie on an arm.  None when there is no room."""
    arm_boxes = [_arm_box(arm) for arm in plan.arms]
    width, height = plan.field
    for avoid_arms in (True, False):
        for box, x, y, anchor in _label_candidates(seat):
            if box[0] < 0 or box[1] < 0 or box[2] > 2 * width or box[3] > 2 * height:
                continue
            if avoid_arms and any(_overlap(box, other) for other in arm_boxes):
                continue
            if any(
                _distance2_to_box(t.cx, t.cy, box) < (2 * SEAT_KEEP_OUT) ** 2
                for t in plan.seats
                if t.number != seat.number
            ):
                continue
            return box, x, y, anchor
    return None


def _badge_spots(seat: _Seat, field: _Field) -> list[tuple[int, int]]:
    """The badge centres that fit into the field, in the order they are taken."""
    spots = []
    for dx, dy in _BADGE_SPOTS:
        x, y = seat.cx + 2 * dx, seat.cy + 2 * dy
        if (
            2 * BADGE_RADIUS <= x <= 2 * (field.width - BADGE_RADIUS)
            and 2 * BADGE_RADIUS <= y <= 2 * (field.height - BADGE_RADIUS)
        ):
            spots.append((x, y))
    return spots


# --------------------------------------------------------------------------
# Public layout functions
# --------------------------------------------------------------------------


def expand_seats(table: Any) -> list[tuple[str, str]]:
    """(arm id, side) of every seat, by number (index 0 is seat 1)."""
    return [(seat.arm.id, seat.side) for seat in _checked(table).seats]


def badge_capacity(table: Any, number: int) -> int:
    """How many dietary badges fit at a seat: 4, at the edge of the field fewer."""
    plan = _checked(table)
    if not _is_int(number) or not 1 <= number <= len(plan.seats):
        raise TableError(f"number: expected a seat number from 1 to {len(plan.seats)}")
    return min(MAX_BADGES, len(_badge_spots(plan.seats[number - 1], plan.field)))


def guest_scheme(table: Any, *, own_seats: Sequence[int], mine_text: str) -> dict:
    """The `scheme` object of a guest page.

    `own_seats` are the seats of the guest record, the guest's own first;
    each of them is drawn in a colour of its own, by its place in the record
    (`SEAT_COLOURS`).  Only the one seat of a record of one seat gets the
    "You" label (`check_table` makes sure that it fits at any seat); the
    seats of a larger record are told apart by their colours alone.  Every
    other seat is a plain one: the guest plan has no couple, no couple
    label, no badges and no dietary marks.  `mine_text` ("Olga — blue") is
    worded by the caller.

    Raises TableError when the table does not pass `check_table` or the
    parameters contradict it, more seats than colours among them.
    """
    plan = _checked(table)
    total = len(plan.seats)
    own = _seat_numbers(own_seats)
    if own is None or not own or len(set(own)) != len(own) or not all(1 <= n <= total for n in own):
        raise TableError(f"own_seats: expected different seat numbers from 1 to {total}")
    if len(own) > len(SEAT_COLOURS):
        raise TableError(f"own_seats: expected at most {len(SEAT_COLOURS)} seats, one per colour")
    if not isinstance(mine_text, str):
        raise TableError("mine_text: expected a string")
    seats = _seat_entries(plan, own=own, couple=set(), flagged=set())
    labels = []
    single = len(own) == 1
    if single:
        spot = _label_spot(plan.seats[own[0] - 1], plan)
        if spot is None:  # pragma: no cover - check_table leaves room at every seat
            raise TableError(f"seat {own[0]}: no room for the 'You' label")
        _box, x, y, anchor = spot
        labels.append({"x": _px(x), "y": _px(y), "anchor": anchor})
    return _scheme(plan, None, seats, [], labels, hidden=False, mine=mine_text, single=single)


def staff_scheme(
    table: Any,
    *,
    couple_seats: Sequence[int],
    couple_label: str | None,
    couple_arm: str | None,
    letters: Mapping[int, Sequence[str]],
) -> dict:
    """The `scheme` object of the staff page.

    `letters` maps a seat number to the letters of its dietary notes in the
    order of the legend; such a seat is marked and gets a badge per letter.
    The seats of the couple and the couple label are drawn; there are no
    seats of a guest, no colours of them and no "You" label.
    """
    plan = _checked(table)
    total = len(plan.seats)
    if not isinstance(letters, Mapping):
        raise TableError("letters: expected a mapping of seat numbers to letters")
    flagged = {}
    for number, items in letters.items():
        if not _is_int(number) or not 1 <= number <= total:
            raise TableError(f"letters: expected seat numbers from 1 to {total} as keys")
        if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
            raise TableError(f"letters: expected a list of letters for seat {number}")
        if not all(isinstance(letter, str) and letter for letter in items):
            raise TableError(f"letters: expected non-empty strings for seat {number}")
        if items:
            flagged[number] = list(items)
    couple, caption = _couple_input(plan, couple_seats, couple_label, couple_arm)
    seats = _seat_entries(plan, own=[], couple=set(couple), flagged=set(flagged))
    badges = []
    for number in sorted(flagged):
        items = flagged[number]
        spots = _badge_spots(plan.seats[number - 1], plan.field)
        if len(items) > min(MAX_BADGES, len(spots)):
            raise TableError(f"seat {number}: no room for {len(items)} badges")
        for letter, (x, y) in zip(items, sorted(spots[: len(items)], key=lambda p: (p[1], p[0]))):
            badges.append({"letter": letter, "cx": _px(x), "cy": _px(y), "r": BADGE_R})
    return _scheme(plan, caption, seats, badges, [], hidden=True, mine="", single=False)


def _couple_input(
    plan: _Plan, couple_seats: Sequence[int], couple_label: str | None, couple_arm: str | None
) -> tuple[list, _Caption | None]:
    total = len(plan.seats)
    couple = _seat_numbers(couple_seats)
    if (
        couple is None
        or len(couple) > 2
        or len(set(couple)) != len(couple)
        or not all(1 <= n <= total for n in couple)
    ):
        raise TableError(f"couple_seats: expected 0-2 different seat numbers from 1 to {total}")
    if couple_arm is not None and (not isinstance(couple_arm, str) or couple_arm not in plan.ids):
        raise TableError("couple_arm: not an id of table.arms")
    if couple_label is None:
        return couple, None
    if not _one_line(couple_label):
        raise TableError("couple_label: expected a non-empty one-line string or None")
    if not couple and couple_arm is None:
        raise TableError("couple_label: needs a couple seat or a couple arm")
    return couple, _caption(plan, couple, couple_label, couple_arm)


def _seat_entries(plan: _Plan, *, own: Sequence[int], couple: set, flagged: set) -> list[dict]:
    """The seats of a plan; `own` are the seats of a guest in the order of
    the record: each takes the colour of its place."""
    colours = dict(zip(own, SEAT_COLOURS))
    entries = []
    for seat in plan.seats:
        number = seat.number
        kind = "you" if number in colours else "couple" if number in couple else "regular"
        mark = "flagged" if number in flagged else "none"
        radius = YOU_R if kind == "you" else FLAG_R if mark == "flagged" else SEAT_R
        entries.append({
            "number": str(number),
            "cx": _px(seat.cx),
            "cy": _px(seat.cy),
            "r": radius,
            "kind": kind,
            "mark": mark,
            "colour": colours.get(number, ""),
            "ring": kind == "you",
            "ringR": RING_R,
        })
    return entries


def _scheme(
    plan: _Plan,
    caption: _Caption | None,
    seats: list,
    badges: list,
    labels: list,
    *,
    hidden: bool,
    mine: str,
    single: bool,
) -> dict:
    couple = None
    if caption is not None:
        couple = {
            "text": caption.text,
            "x": _px(caption.x),
            "y": _px(caption.y),
            "vertical": caption.vertical,
        }
    return {
        "width": str(plan.field.width),
        "height": str(plan.field.height),
        "hidden": hidden,
        "tableLabel": plan.label,
        "total": str(len(plan.seats)),
        "mine": mine,
        "single": single,
        "outline": plan.outline,
        "couple": couple,
        "seats": seats,
        "badges": badges,
        "labels": labels,
    }
