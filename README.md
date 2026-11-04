# Personal dinner menus

A builder of static personal dinner-menu pages: one page per guest (their
seats, the menu, drinks) and one staff page for the restaurant, each at its own
secret address. It is the companion of a builder of personal invitations.

The principles behind all of the code:

- **static pages only** - no server, no database, no forms; the data is put
  into the HTML when the pages are built;
- **privacy by construction** - a guest's page holds nothing about other
  guests, and no page makes a single request to another domain;
- **progressive enhancement** - everything on a page is readable without
  JavaScript;
- **code and data kept apart** - this repository holds only code and fictional
  examples.

## Status

The builder works: it checks the data, builds the pages and checks the
finished output. The example data sets in `examples/` show every part of the
data format.

## What's where

```
build.py               command line entry point: build, validate, links, token
menu_tools/            the package of the builder
  _core.py             the bridge to the invitations builder in site/: all that is taken from it
  _schema.py           the checks of menu.json and guests.json
  _page.py             the page trees of the guests and of the staff
  _words.py            the words the build joins with numbers and names
  _table.py            the table plan: seat numbers, layout, the scheme
  _output.py           the checks of the finished output
template.html          the page template
fragments/             the fragments of the sections, the widgets and their parts
  partials/section-nav.html   the line of the sections at the top of a page
  widgets/heading.html        the heading of a part of a section
assets/                the style sheet and the script of the pages
examples/data/         fictional data: an L-shaped table of 19 seats, dietary notes, a staff page
examples/data-plain/   fictional data without a table and dietary notes
site/                  submodule: the code of the invitations builder, pinned to a commit
tests/                 unit tests (unittest, standard library only)
.github/workflows/     unit tests, repository hygiene, builds of the examples and their checks
LICENSE                the MIT license
```

## Sections and navigation

`sections` of `menu.json` are the sections of a page in their order: the
cover (`"type": "cover"`, first) and sections of widgets. A widget is a text,
the seating, a list of dishes, the set switcher, the drinks or a heading.
`audience` (`all`, `guest` or `staff`) and `visible` choose the pages a
section or a widget is on; a guest record can switch them for its own page.

- `nav` of a section is the short label of its link in the line of the
  sections at the top of the page: one line of text, not empty. A section
  without it (the closing signature, say) has no link there, and a page links
  only the sections it shows. The cover has no label; two sections with the
  same label (letter case aside) get a warning.
- A widget of the type `heading` heads a part of its section: `title` (an
  h3), `eyebrow` in small capitals under it, and `staff: { title, eyebrow }`
  for the staff page. The widgets after it, up to the next heading, are its
  part; a set card in a part is an h4. A heading with nothing under it on a
  page is left out of that page, and `validate` warns about a heading at the
  end of a section or right before another one. `title` of a list of dishes
  stays a caption in small capitals, not a heading.

The line is a row of plain links to the sections of the page: nothing is
hidden, and without JavaScript a link jumps to its section. With it, the link
of the section in view is marked (`aria-current`), and a click keeps the mark
of its link while the page scrolls there. On the screen the line sticks to
the top, a section reached by a link stops under it, the scroll glides unless
the reader asks for less motion, and a line too long for the screen scrolls
sideways by itself; on a touch screen the body scrolls the page. Print leaves
the line out.

A page links only to its own parts: every `<a>` and `<area>` of the output has
an `href` of the form `#<id>`, the id of an element of the same page. The
build and CI refuse any other link, and no file of the output holds a token.

The food of `examples/data`, one section of two parts (a few fields left out):

```json
{
  "id": "food",
  "title": "Food",
  "nav": "Food",
  "widgets": [
    {
      "type": "heading",
      "title": "Starters",
      "eyebrow": "Shared plates for the table",
      "staff": { "eyebrow": "Shared plates · on the table by 19:15" }
    },
    { "type": "dishes", "items": ["bruschetta", "cheese-board", "hummus"] },
    { "type": "dishes", "audience": "staff", "title": "On request", "items": ["melon"] },
    {
      "type": "heading",
      "title": "Main course",
      "eyebrow": "Choose one of two sets",
      "staff": { "eyebrow": "Two sets · guests choose at the table" }
    },
    { "type": "sets", "items": ["fish", "meat"] },
    { "type": "text", "id": "allergy-card", "audience": "guest", "variant": "card", "text": "…" }
  ]
}
```

## The table plan

`table` of `menu.json` is the plan of the seats on the pages. `arms` are the
rectangles of the table (`id`, `x`, `y`, `width`, `height`, in px of the
field: 318 x 310 unless the table sets `width` and `height` of its own, see
below); each item of `seats` puts `count` seats (one by default) on a
side of an arm: `top`, `right`, `bottom` or `left`. A seat's number is its
place in the list, and the seats of a side go clockwise. The build centres
the seats of a side on its free part, 22 px off the edge of the table and
42 px apart; only when they do not fit at 42 px are they spread evenly over
the free part, the outer seats 15 px from its ends, with a warning, down to
34 px apart. A side ends 22 px before an arm that adjoins it, so the
corner between two arms stays free. `shift` of an arm moves the seats of a
side along it, by at most 42 px.

`align` of an item lines its seats up with other seats: an element per seat
of the item, in the order of their numbers - the number of another seat, or
`null` for a seat that the layout places. A seat with a number takes the
coordinate of that seat along its own side (x on the top and the bottom, y
on the left and the right) and keeps its distance from the edge of the
table. The other seats of its side are placed around the aligned ones:

- between two aligned seats - evenly;
- before the first and after the last aligned seat - 42 px apart, outwards
  from it; when they do not fit into the free part of the side (the outer
  seat 15 px from its end), evenly between that point and the aligned seat,
  with the usual warning below 42 px and an error below 34 px.

A side without numbers in `align` keeps the layout above, and `shift` has no
effect on a side with aligned seats. A seat may align to a seat that comes
later in the list, and alignments may form a chain. `validate` and `build`
refuse an alignment to the seat itself or to a seat of the same side of the
same arm, a circle of alignments, and a seat lined up off the free part of
its side (off the table or into the free corner) or out of the clockwise
order of its side.

An L-shaped table of 19 seats: the first seat of the right side (8) faces
the seat at the end of the long arm (1), the last seat of the top row (7)
sits over the seat at the end of the short arm (12), and seats 13 and 14
inside the short arm face seats 11 and 10:

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

Seats 9-11 follow seat 8 at 42 px. Seats 2-6 do not fit at 42 px to the
left of seat 7, so they are spread from the left end of the top side to it,
40.5 px apart, with a warning (as for the five seats of the bottom side,
which do not fit either).

`width` and `height` of `table` set the size of the field, in px: whole
numbers, `width` from 240 to 480 and `height` from 160 to 640, both
optional (318 and 310 by default). Every arm and every seat with the room
for its "You" label has to lie inside the field; `validate` names a size
out of its limits and an arm or a seat off the field ("lies outside the
360x310 field"). The plan is drawn as many px wide as its field on a wide
screen; on a narrow one it shrinks to the width of its card, keeping its
proportions, its type with it, and never scrolls sideways - hence the upper
limit of the width: on the narrowest phones a field of 480 is drawn at
about 0.6 of its size, its 12 px type at about 7 px. An L-shaped table on
18 seats in a wider field, both arms 32 px thick: seat 8, the last of the
top row, sits over the middle of the short arm (`shift` moves the row by
1 px for it), the six seats under the long arm line up with the seats over
it, seat 9 with seat 1 and seat 12 with seat 11:

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

A guest page names no seat by its number. Its plan shows the seats of the
record as larger circles, each in a colour of its own in the order of the
seats of the record - blue (the accent), dark red, green - and under the plan
a label of the same colour per seat names who sits there: the name of the
seat, the name of the record at a first seat without one, "your guest" at a
+1 without a name. The one seat of a record of one seat has the label "You"
by it as well. The colours differ in lightness enough to tell them apart in
grey and with a colour vision deficiency, and the text of the plan for a
screen reader says in words whose seat is marked in which colour. So a
record has at most three seats: `validate` and `build` refuse more (split
such a record in two). The couple, its label and the numbers of the seats
are on the staff plan alone.

## Commands

| Command | What it does |
|---|---|
| `python3 build.py build [--data DIR] [--out DIR] [--base-path PATH]` | checks the data, writes `<token>/index.html` for every guest record and for the staff record and `assets/` into `--out` (default: `dist`), which is replaced only when every check of the output has passed |
| `python3 build.py validate [--data DIR]` | checks the data and prints a summary; writes nothing |
| `python3 build.py links --url URL [--data DIR]` | prints the name of every guest record and the address of its page, `URL/<token>/`, the staff page last; the lines hold personal data, so the command is for local use only and refuses to run in CI |
| `python3 build.py token [--prefix NAME]` | prints a new token: fully random (for the staff record) or readable, `NAME-xxxx` |

`--data` is a directory with `menu.json` and `guests.json` (default:
`examples/data` next to `build.py`). `--base-path` is the path from the root of
the site under which the output is published (default: `/`).

Exit codes: `0` - success; `1` - errors in the data or in the finished output,
an `--out` that is not replaced, `links` in CI, or the submodule `site/` is not
checked out; `2` - a bad command line.

## Tests

Python 3.10 or newer is required; there are no third-party packages. The
code of the invitations builder comes with the submodule:

```
git submodule update --init --recursive
python3 -m unittest discover -s tests -t .
```

## License

MIT, see [LICENSE](LICENSE).
