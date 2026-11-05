# Personal dinner menus

Static per-guest dinner menus with a seat plan, plus a staff sheet, built
from two JSON files.

Every guest gets a page of their own at a secret address: the menu, the
drinks and a plan of the table with their seats marked. The restaurant gets
one staff page with every seat, every dietary need and what to serve
instead. A Python script checks the data, builds the pages and checks them
again before it writes them.

## Features

- **A page per guest.** The menu, the set menus to choose from, the drinks,
  and a table plan with the guest's seats in colour. One page can serve a
  guest and up to two companions.
- **A staff sheet.** The plan with dietary badges and a legend, a seat table
  with names and needs, a swap line for every dish a seat cannot have
  ("Seat 4 — serve a portion without walnuts"), the drinks with bottles and
  serving notes.
- **Privacy.** Secret addresses, no data about other guests on a guest's
  page, no requests to other servers, `noindex` on every page.
- **Works without JavaScript.** Everything on a page is readable without
  it; the script adds tabs for the set menus, marks the current section in
  the navigation bar and fades the sections in.
- **Any language.** English by default; two fields in `menu.json`
  translate every word on the pages, with plural rules built in.
- **Python standard library only.** Python 3.10 or newer, no packages, no
  build tools.
- **Reproducible, self-checked output.** The same data always gives
  byte-identical output, and a build replaces the previous one only after
  every output check has passed.

## Quick start

From the root of the repository, with the fictional example data in
`examples/data`:

```
python3 build.py validate
```

checks the data and prints a summary:
`validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), 2 set(s), 5 drink(s)`.

```
python3 build.py build
```

writes the pages into `dist/`: a directory per page, named after the
record's token, and `assets/`.

```
python3 build.py links --url http://localhost:8000
```

prints the address of every page, a guest per line and the staff page last:

```
Greta	http://localhost:8000/egret-xnmg/
Peggy and Walter	http://localhost:8000/plover-32fe/
...
staff	http://localhost:8000/DmFnSjs_glP7Qu8z8_MRKw/
```

```
python3 -m http.server -d dist 8000
```

serves the pages. Open one of the printed addresses in a browser: a guest's
page, or the staff page from the last line.

### Your own dinner

1. Copy `examples/data` to `../my-dinner`, outside this repository: the data
   holds names, and this repository holds only code and fictional examples.
2. Write the menu into `menu.json` and the guests into `guests.json` (see
   [the data in brief](#the-data-in-brief)). Make a readable token for each
   guest with `python3 build.py token --prefix Greta`, and a random one for
   the staff with `python3 build.py token`.
3. Check the data until it passes:
   `python3 build.py validate --data ../my-dinner`.
4. Build it for the path where it will be published:
   `python3 build.py build --data ../my-dinner --out ../my-dinner-pages --base-path /menu`.
5. Upload the contents of `../my-dinner-pages` to `/menu/` on any static
   host, then print the links and send each guest theirs:
   `python3 build.py links --data ../my-dinner --url https://example.org/menu`.

## How it works

1. **Data.** `build.py` reads `menu.json` and `guests.json` from the data
   directory.
2. **Checks.** It checks both files and reports every problem at once,
   naming the place in the data without quoting it.
3. **Pages.** It builds each guest page from two parts only: the shared menu
   without its staff-only parts, and the guest's own record. The staff page
   gets everything.
4. **Template.** It renders each page with `template.html` and the fragments
   in `fragments/`, next to the style sheet and the script in `assets/`.
5. **Output checks.** It writes the output to a new directory beside
   `--out`, checks it (expected files only, local addresses only, no token in
   any file) and only then swaps it in.

## Privacy model

- **Secret addresses.** A page lives at `<base path>/<token>/`. There is no
  index page, and no output file contains a token, not even the page it
  names.
- **Nothing about others.** A guest page is built from the shared menu and
  the guest's own record alone: no other guest, no dietary needs, no seat
  numbers, no hosts' seats. The staff page holds no token and no guest's
  personal note.
- **No requests to other servers.** No web fonts, analytics or embeds; the
  style sheet, the script and the icon come from the page's own `assets/`,
  with no inline script or style, and every link leads to a part of the same
  page.
- **Kept out of search and previews.** Every page asks search engines to
  keep away (`noindex, nofollow`), sends no referrer and has no link-preview
  tags.
- **Quiet tools.** Messages never quote the data and hide tokens in paths;
  `links`, the one command that prints names and addresses, refuses to run
  in CI.

## The data in brief

A menu without a table: a cover, a staff-only seat list and the food.

```json
{
  "schemaVersion": 1,
  "coupleNames": "Ada & Ben",
  "event": {
    "title": "Birthday dinner",
    "when": "3 May 2031, 19:30",
    "place": "Example Bistro · Example Street 1"
  },
  "dishes": {
    "soup": { "name": "Pumpkin soup", "ingredients": "Pumpkin, ginger, cream" },
    "risotto": { "name": "Mushroom risotto", "ingredients": "Rice, mushrooms, parmesan" }
  },
  "sections": [
    { "id": "cover", "type": "cover" },
    { "id": "seats", "nav": "Seats", "audience": "staff", "widgets": [{ "type": "seating" }] },
    { "id": "food", "title": "Food", "nav": "Food", "widgets": [{ "type": "dishes", "items": ["soup", "risotto"] }] }
  ]
}
```

`coupleNames` names the hosts of the dinner, whoever they are. `guests.json`
holds one record per page, plus the staff record:

```json
[
  { "token": "Clara-7hqe", "name": "Clara", "seats": [{ "number": 1 }] },
  {
    "token": "Dan-and-Eve-p4xw",
    "name": "Dan and Eve",
    "seats": [{ "number": 2, "name": "Dan" }, { "number": 3, "name": "Eve" }]
  },
  { "token": "ElGMUjWqGAfAa53K7D5-jQ", "staff": true }
]
```

Add dietary `requirements` and `allergens`, set menus, drinks, a `table`,
texts and headings, sections hidden for most guests and shown for a few.
The examples use most of the format; [the data format](docs/data-format.md)
describes all of it.

## The table plan

`table` in `menu.json` draws the table on every page. In brief:

- `arms` are rectangles in a field of 318 x 310 px (or `width` x `height`);
- each item of `seats` puts `count` seats on one side of an arm, and a
  seat's number is its place in that list, clockwise on each side;
- the build centres the seats of a side 42 px apart, 22 px off the edge,
  and squeezes them, with a warning, when they do not fit;
- `align` lines a seat up with another one, across the table or round a
  corner;
- `validate` refuses seats closer than 34 px, a seat off the field and a
  side split in two by another arm.

An L-shaped table of 19 seats, in which seat 8 faces seat 1, seat 7 sits over
seat 12, and seats 13 and 14 face seats 11 and 10:

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

A guest's plan marks the guest's seats in colour and names no seat by its
number; the staff plan numbers every seat and shows the dietary badges.
[The table plan](docs/table-plan.md) gives the full geometry and a second
example.

## Languages

`lang` (a language tag such as `de` or `sr-Latn`) and `strings` (the words
of the pages) in `menu.json` translate the pages. An English menu may change
a single word, such as the page title:

```json
{ "strings": { "pageTitle": "Supper" } }
```

A menu in another language gives every word; `validate` lists the missing
ones. [Languages](docs/languages.md) has every key, the plural rules and a
complete sample in Serbian (Latin script).

## Documentation

- [Command line](docs/cli.md): the commands, their options, the output
  directory, the messages and the exit codes.
- [Data format](docs/data-format.md): every field of `menu.json` and
  `guests.json`, the sections and the widgets.
- [Table plan](docs/table-plan.md): the geometry of the plan, alignment, the
  guest's and the staff plan.
- [Languages](docs/languages.md): `lang`, `strings`, plural forms, scripts and
  fonts.

## Development

Python 3.10 or newer; there are no third-party packages. The tests use
`unittest`:

```
python3 -m unittest discover -s tests -t .
```

CI runs the tests on Python 3.10 to 3.13, checks the repository's hygiene
(no tracked media or build output), builds both example sets, one of them
under a base path, checks the built pages and builds once more to compare
the bytes.

`BUILD_DEBUG=1` shows the traceback of an unexpected failure, which the
commands otherwise report by its type and place only.

## Licence

MIT, see [LICENSE](LICENSE).
