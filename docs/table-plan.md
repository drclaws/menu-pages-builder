# Table plan

`table` in `menu.json` describes the table that the seating widget draws: a
plan of the seats on every guest page and on the staff page. The field is
optional; a menu without it has no plan, and seat numbers then only name the
seats (see [Seats without a table](#seats-without-a-table)).

All sizes are in px of the plan's field, the coordinate system of the drawing.
The build works in whole half pixels, so the output is the same on every
platform.

## Fields

| Field | Type | Rules |
|---|---|---|
| `label` | text, required | The table's name: a pill on the staff cover and part of the plan's text for screen readers ("L-shaped table"). |
| `width` | whole number | Width of the field, 240 to 480. Default 318. |
| `height` | whole number | Height of the field, 160 to 640. Default 310. |
| `arms` | array, required | The rectangles of the table, at least one. |
| `seats` | array, required | Groups of seats on the sides of the arms, at least one. |

An **arm** is one rectangle:

| Field | Type | Rules |
|---|---|---|
| `id` | text, required | a-z, 0-9 and `-`, starting with a letter, at most 40 characters; unique among the arms. |
| `x`, `y` | whole numbers, required | The top left corner. |
| `width`, `height` | whole numbers, required | At least 20 each. The arm must lie inside the field. |
| `shift` | object | Moves the seats of a side along it: `{ "top": -1 }`. Keys are sides, values whole numbers from -42 to 42. |

Arm ids follow their own rule: unlike the ids of the rest of the data, they
may hold several hyphens in a row and may be up to 40 characters long.

A **seat item** puts one or more seats on one side of an arm:

| Field | Type | Rules |
|---|---|---|
| `arm` | text, required | The `id` of an arm. |
| `side` | text, required | `top`, `right`, `bottom` or `left`. |
| `count` | whole number | 1 to 20 seats. Default 1. |
| `align` | array | One element per seat of the item: the number of another seat, or `null`. See [Aligned seats](#aligned-seats). |

A table has at most 99 seats: a three-digit number does not fit into a seat.

## Seat numbers

A seat's number is its place in the expanded list of `seats`: the first item
gives seat 1 (or seats 1 to `count`), the next item continues from there. The
seats of one side go clockwise round the table: left to right on the top,
downwards on the right, right to left on the bottom, upwards on the left.

Several items may name the same side of the same arm; their seats form one
row, in the order of their numbers.

## Layout of a side

The build places each seat centre 22 px off the edge of its arm and centres
the seats of a side on the side's free part, 42 px apart. The free part is
the side without the length that another arm covers. Where another arm
adjoins the side, the free part ends 22 px before it, so the corner between
two arms stays free.

When the seats do not fit at 42 px, they are spread evenly over the free
part, the outer seats 15 px from its ends, and `validate` warns that the side
is squeezed. Seats closer than 34 px are an error. A side covered entirely by
another arm, or split in two by one, is an error too: make two arms of it.

`shift` of an arm moves the whole row of a side along it, by at most 42 px.
It has no effect on a side with aligned seats.

## Aligned seats

`align` lines seats up with other seats. Its elements follow the seats of the
item in the order of their numbers: the number of another seat, or `null` for
a seat that the layout places. A seat with a number takes the coordinate of
that seat along its own side (x on the top and the bottom, y on the left and
the right) and keeps its 22 px from the edge of the table.

The other seats of the side are placed around the aligned ones:

- between two aligned seats, evenly;
- before the first and after the last aligned seat, 42 px apart, outwards from
  it. When they do not fit into the free part (the outer seat 15 px from its
  end), they are spread evenly between that point and the aligned seat, with
  the usual warning below 42 px and an error below 34 px.

A seat may align to a seat that comes later in the list, and alignments may
form a chain. `validate` and `build` refuse:

- an alignment to the seat itself or to a seat on the same side of the same
  arm;
- a circle of alignments;
- a seat lined up off the free part of its side (off the table or into the
  free corner);
- a seat lined up out of the clockwise order of its side.

## The field

Every arm, and every seat with the room for the label of a guest's seat
("You"), must lie inside the field. `validate` names a size out of its limits
and an arm or a seat off the field ("lies outside the 360x310 field").

On a wide screen the plan is drawn as many px wide as its field. On a narrow
one it shrinks to the width of its card, keeping its proportions and scaling
its type with it, and never scrolls sideways. Hence the upper limit of the
width: on the narrowest phones a field of 480 is drawn at about 0.6 of its
size, its 12 px type at about 7 px.

## Example: 19 seats

An L-shaped table of 19 seats. The first seat on the right side (8) faces the
seat at the end of the long arm (1); the last seat of the top row (7) sits
over the seat at the end of the short arm (12); seats 13 and 14, inside the
short arm, face seats 11 and 10.

```json
{
  "label": "L-shaped table",
  "arms": [
    { "id": "long", "x": 39, "y": 40, "width": 240, "height": 44 },
    { "id": "short", "x": 235, "y": 40, "width": 44, "height": 170 }
  ],
  "seats": [
    { "arm": "long", "side": "left" },
    { "arm": "long", "side": "top", "count": 6, "align": [null, null, null, null, null, 12] },
    { "arm": "short", "side": "right", "count": 4, "align": [1, null, null, null] },
    { "arm": "short", "side": "bottom" },
    { "arm": "short", "side": "left", "count": 2, "align": [11, 10] },
    { "arm": "long", "side": "bottom", "count": 5 }
  ]
}
```

Seats 9 to 11 follow seat 8 at 42 px. Seats 2 to 6 do not fit at 42 px to the
left of seat 7, so they are spread from the left end of the top side to it,
40.5 px apart. `validate` warns about this side, and about the five seats of
the bottom side, which do not fit at 42 px either.

## Example: 18 seats in a wider field

An L-shaped table of 18 seats in a field 360 px wide, both arms 32 px thick.
Seat 8, the last of the top row, sits over the middle of the short arm: the
`shift` moves the row by 1 px for it. The six seats under the long arm (13 to
18) line up with seats 7 to 2 over it; seat 9 faces seat 1, and seat 12 faces
seat 11.

```json
{
  "label": "L-shaped table",
  "width": 360,
  "height": 310,
  "arms": [
    { "id": "long", "x": 39, "y": 40, "width": 282, "height": 32, "shift": { "top": -1 } },
    { "id": "short", "x": 289, "y": 40, "width": 32, "height": 120 }
  ],
  "seats": [
    { "arm": "long", "side": "left" },
    { "arm": "long", "side": "top", "count": 7 },
    { "arm": "short", "side": "right", "count": 3, "align": [1, null, null] },
    { "arm": "short", "side": "left", "align": [11] },
    { "arm": "long", "side": "bottom", "count": 6, "align": [7, 6, 5, 4, 3, 2] }
  ]
}
```

This table passes without a warning: every row keeps 42 px.

## The guest's plan

A guest page names no seat by its number. Its plan shows the record's seats as
larger circles, each in a colour of its own, in the order of the record's
seats: blue (the accent), dark red, green. Under the plan a label of the same
colour per seat says who sits there:

- the seat's `name`;
- the record's `name` at a first seat without one;
- "your guest" at a +1 without a name.

The one seat of a single-seat record also has the label "You" by it. The
colours differ in lightness enough to tell them apart in grey and with a
colour vision deficiency, and the plan's text for screen readers says in words
whose seat has which colour. So a record has at most three seats: `validate`
and `build` refuse more (split such a record in two).

Every seat of the table needs room for the "You" label, since any seat can be
a guest's only seat. The room is estimated from the word: about 7 px per
character, at least 26 px. A longer word in another language may give the
error "no room for the label of the guest's seat" (see
[Languages](languages.md#the-label-of-a-guests-seat)).

A guest's plan shows no couple, no couple label, no dietary badges and no
seat numbers.

## The staff plan

The staff plan shows every seat with its number. A seat with dietary
requirements is marked, with a badge per requirement letter around it: up to
four, fewer at the edge of the field. `validate` refuses a seat with more
requirements than it has room for.

The seats of the hosts (`couple.members`) have a style of their own, and
`couple.label` is written in capitals inside an arm: `couple.arm`, or the arm
of the first member's seat. The label is centred on the free part of the arm,
along its longer side. Its width is estimated, not measured, and `validate`
warns when it may not fit.

The seat table under the plan has a row per seat: the number, the name, a role
or whose guest a +1 is, and the dietary requirements. A seat that nobody takes
shows a dash. Screen readers skip the staff plan: the seat table says the same
in text. List a seat that stays free on purpose in `reservedSeats`;
`validate` warns about any other free seat.

## Seats without a table

Without `table`, seat numbers are any whole numbers from 1 to 999 and only
name the seats in the data: a guest page shows the names of the record's seats
and no plan, and the staff seat table lists the taken seats in order.
`reservedSeats`, `couple.label` and `couple.arm` have no effect, and
`validate` says so.
