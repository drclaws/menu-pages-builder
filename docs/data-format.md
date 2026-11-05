# Data format

A data set is a directory with two JSON files, read as UTF-8:

- `menu.json`: the dinner, shared by every page: the event, the dishes, sets
  and drinks, the table, the sections of the pages;
- `guests.json`: the guest records, one page each, and the staff record.

`examples/data` and `examples/data-plain` use most of the format; this page
describes all of it. `python3 build.py validate --data DIR` checks a data set
against these rules (see [Command line](cli.md)).

## General rules

- **Unknown fields are errors**, with a suggestion for a misspelt name. JSON
  has no comments, and a key such as `"_note"` is an unknown field too.
- **Texts** are one line unless a field says otherwise. An empty text, or one
  of spaces only, counts as not set; a required text must not be empty.
  `null` is never accepted.
- **Several lines.** Where a text may have several lines, a blank line starts
  a new paragraph and a single line break becomes a line break.
- **No template syntax.** No text may hold `{{`, `}}` or `{token}`.
- **Ids** are 1 to 32 characters: lower-case a-z, 0-9 and single hyphens,
  starting with a letter (`cheese-board`, `set-2`). They are ASCII, since
  they become parts of HTML ids, and no reader sees them. Arm ids follow
  their own rule (see [Table plan](table-plan.md#fields)).
- **Dates are free text**: the build shows `event.when` and `staff.updated`
  as written.
- **Lists by id.** Requirements, allergens, dishes, sets, drink categories
  and drinks are objects keyed by their ids, `{ "id": { ... } }`. The order
  of `requirements` is the order of the legend and of a seat's badges and
  pills; widgets list dishes, sets and drinks in an order of their own.

## menu.json

| Field | Type | Meaning |
|---|---|---|
| `schemaVersion` | number, required | `1`. |
| `lang` | text | The language of the pages, `en` by default. See [Languages](languages.md). |
| `strings` | object | The words of the pages. See [Languages](languages.md). |
| `coupleNames` | text, required | The names of the hosts of the dinner, as the pages show them: "Linus & Maren". |
| `event` | object, required | `title`, `when` and `place`, each a required text. |
| `staff` | object | The texts of the staff page. |
| `requirements` | object | Dietary requirements, by id. |
| `allergens` | object | Allergens, by id. |
| `couple` | object | The hosts at the table. |
| `reservedSeats` | array | Seats that stay free on purpose. |
| `table` | object | The table plan. See [Table plan](table-plan.md). |
| `dishes` | object | Dishes, by id. |
| `sets` | object | Set menus, by id. |
| `drinks` | object | Drink categories and drinks. |
| `sections` | array, required | The sections of the pages, in order. |

### The event and the hosts

`event.title` is the main heading of a guest page; `event.when` and
`event.place` stand under it. The staff page shows the time as its heading.

`coupleNames` and `couple` name **the hosts of the dinner**: a couple, as the
field names say, or whoever gives the dinner. `coupleNames` stands above the
event title and in the page title ("Dinner menu · Linus & Maren").

`couple` places the hosts at the table. Only the staff page shows them; a
guest page holds nothing of it.

| Field | Type | Meaning |
|---|---|---|
| `label` | text | Written in capitals inside an arm of the staff plan: "Linus · Maren". |
| `arm` | text | The `id` of the arm for the label. Default: the arm of the first member's seat. |
| `members` | array, required | One or two hosts. |

A member:

| Field | Type | Meaning |
|---|---|---|
| `seat` | number, required | The host's seat. |
| `name` | text, required | The name in the staff seat table. |
| `role` | text | Shown after the name in the staff seat table: "host". |
| `requirements` | array | Requirement ids, as for a guest's seat. |

### staff

| Field | Type | Meaning |
|---|---|---|
| `updated` | text | The date of the last change, in the bar at the top of the staff page: "updated 12 June 2030". |
| `contact` | text | Who to call during the dinner, in the footer: "Contact on the night: …". |
| `reminder` | text, several lines | A note in the footer of the staff page. |

### requirements and allergens

A **requirement** is a dietary need of a seat: "no nuts", "vegan".

| Field | Type | Meaning |
|---|---|---|
| `letter` | text, required | One capital letter, unique among the requirements: the badge at the seat on the staff plan and in the legend. Any script: "N", "Č". |
| `label` | text, required | The text of the legend and of the swap lines of a set: "no nuts". |
| `tag` | text | The pill in the staff seat table, when it should differ from `label`: "nut allergy". |
| `avoids` | array | Allergen ids the requirement rules out. |

An **allergen** has one field, `label` (required): the orange pill of a dish
on the staff page.

`avoids` connects the two. When the staff page shows a dish that holds an
allergen a requirement avoids, a seat has that requirement, and the dish has
no swap for it, `validate` warns: the waiter would get no instruction.

A requirement that no seat uses is left out of the legend, and `validate`
warns about it, as about an allergen that no dish or requirement uses.

### reservedSeats

A list of seat numbers that stay free all evening. No record and no host may
take them. The staff seat table shows them as free, and `validate` warns
about any other free seat. Without a `table` the list has no
effect.

### table

See [Table plan](table-plan.md). Without a table, seat numbers run from 1 to
999 and the pages show no plan.

### dishes

| Field | Type | Meaning |
|---|---|---|
| `name` | text, required | The dish. |
| `ingredients` | text | Under the name on the guest page. |
| `staff` | object | What only the staff page shows. |

`staff` of a dish:

| Field | Type | Meaning |
|---|---|---|
| `allergens` | array | Allergen ids: an orange pill each. `[]` says the dish has none. |
| `tags` | array of texts | Joined into one grey pill: "vegan · gluten-free". |
| `swaps` | object | Requirement id → what the waiter does for such a seat: "serve the tomatoes on cucumber slices". |
| `note` | text | A line for the waiters: "Only when a guest asks for something else". |

A dish with `"allergens": []` and no tags gets the pill "no restrictions". A
dish on the staff page without `allergens` gets a warning: the staff would see
no allergen information for it.

A swap is shown only when a seat has its requirement. Under a dish of a
dishes widget it reads "Seat 4 — serve a portion without walnuts on a
separate plate"; under a set, "If chosen by seat 4 (no nuts) — serve the
second course without the crust." (the requirement's `label` in brackets).

### sets

A set is a menu of courses for the guests to choose from.

| Field | Type | Meaning |
|---|---|---|
| `title` | text, required | The tab and the heading of the card: "Set A". |
| `hint` | text | Under the title in the tab: "Fish". |
| `eyebrow` | text | Under the heading of the card: "two courses". |
| `courses` | array, required | Dish ids, at least one: the numbered courses. |
| `pairing` | text | Under the courses: "Paired with white wine". |

### drinks

| Field | Type | Meaning |
|---|---|---|
| `categories` | object, required | Categories by id, each with a required `label`: "Sparkling". |
| `items` | object, required | Drinks by id. |

A drink:

| Field | Type | Meaning |
|---|---|---|
| `category` | text, required | A category id: its label stands by the drink. |
| `name` | text, required | The drink. |
| `details` | text | Origin, grape: "Example Valley · Chardonnay". |
| `servedWith` | text | When it is poured: "with the starters". |
| `staff` | object | `bottles` ("6 bottles"), `serving` ("well chilled") and `swaps` (as for a dish: "seat 11 — alcohol-free sparkling"). |

A dish, set or drink that no page shows gets a warning.

## Sections

`sections` lists the sections of the pages in order. Every page is built from
the same list; `audience`, `visible` and the guest records decide what each
page shows.

The **cover** is `{ "id": "cover", "type": "cover" }`: the first section, at
most one, the same for everybody. Without one, a page has no main heading
and `validate` warns.

Every other section holds widgets:

| Field | Type | Meaning |
|---|---|---|
| `id` | id, required | Unique among the sections. Guest records refer to it. |
| `type` | text | `custom`, the default. |
| `title` | text | The heading of the section. Required, except in the section with the seating widget, whose default title is "Your seat" or "Your seats" for a guest and "Seating and dietary notes" for the staff. |
| `eyebrow` | text | A line under the title. |
| `nav` | text | The section's label in the navigation bar. |
| `staff` | object | `title` and `eyebrow` for the staff page, in place of the ones the guests see. |
| `audience` | text | `all` (default), `guest` or `staff`: who sees the section. |
| `visible` | boolean | `false` hides the section by default; a guest record can show it. Default `true`. |
| `widgets` | array, required | The contents of the section. |

A section with nothing to show on a page is left out of that page.

### Audience and visibility

`audience` and `visible` work the same on a section and on a widget:

- `"audience": "guest"` leaves the part out of the staff page;
  `"audience": "staff"` leaves it out of every guest page, and out of the data
  a guest page is built from.
- `"visible": false` hides a part by default. A guest record switches it on
  for its own page (see [Section overrides](#section-overrides)), and the
  staff page then shows it too, since some guest sees it.
- A widget's audience must fit its section's: a staff widget in a guest
  section is an error.

### The navigation bar

The navigation bar at the top of a page is a row of plain links, one per
section with a `nav` label, in page order. A page links only the sections it
shows; the cover has no label. Without JavaScript a link jumps to its
section. With it, the link of the section in view is marked, and the scroll
glides unless the reader asks for less motion. The bar sticks to the top of
the screen, scrolls sideways when its links do not fit, and is left out of
print.

`nav` is one line and must not be empty: leave it out for a section without a
link. Two sections with the same label, letter case aside, get a warning.

### Widgets

Every widget has these fields:

| Field | Type | Meaning |
|---|---|---|
| `type` | text, required | `text`, `seating`, `dishes`, `sets`, `drinks` or `heading`. |
| `id` | id | Unique within its section. Needed only for a guest record to address the widget. |
| `audience` | text | `all` (default), `guest` or `staff`. |
| `visible` | boolean | `false` hides the widget by default. Default `true`. |

#### text

| Field | Type | Meaning |
|---|---|---|
| `text` | text, required, several lines | The text. |
| `variant` | text | `body` (default), `lead` (larger type), `card` (a note in a card) or `signature` (large heading type, for the names under a closing line). |

#### heading

A heading starts a part of its section: the widgets after it, up to the next
heading.

| Field | Type | Meaning |
|---|---|---|
| `title` | text, required | The heading of the part (an h3; a set card under it is an h4). |
| `eyebrow` | text | A line in small capitals under it. |
| `staff` | object | `title` and `eyebrow` for the staff page. |

A page leaves out a heading with nothing under it. `validate` warns about a
heading at the end of a section or right before another heading.

#### seating

The record's seats on a guest page; every seat on the staff page. At most one
seating widget in the menu.

| Field | Type | Meaning |
|---|---|---|
| `showScheme` | boolean | The table plan, on both pages. Default `true`. |
| `showLegend` | boolean | The legend of the requirement letters, on the staff page. Default `true`. |
| `showTable` | boolean | The seat table, on the staff page. Default `true`. |
| `staff` | object | `footnote`: a line under the seat table. |

A guest page shows the plan with the record's seats in colour and, under it,
who sits at each of them (see
[Table plan](table-plan.md#the-guests-plan)). Without a table it shows the
names alone.

#### dishes

| Field | Type | Meaning |
|---|---|---|
| `items` | array, required | Dish ids, at least one. |
| `title` | text | A caption in small capitals over the list, not a heading. |

The guest page shows each dish's name and ingredients; the staff page shows
the name, the allergen pills, the swap lines and the note.

#### sets

| Field | Type | Meaning |
|---|---|---|
| `items` | array, required | Set ids, at least one. |
| `note` | text | A line under the cards, on guest pages. |
| `staff` | object | `note`: the same for the staff page. |

With several sets and JavaScript, the sets become tabs and one card shows at
a time. Without JavaScript the cards follow each other. The tabs only show
the sets: nothing is chosen or sent.

#### drinks

| Field | Type | Meaning |
|---|---|---|
| `groups` | array, required | At least one group. |
| `note` | text | A line under the drinks, on guest pages. |
| `staff` | object | `note`: the same for the staff page. |

A group:

| Field | Type | Meaning |
|---|---|---|
| `items` | array, required | Drink ids, at least one. |
| `title` | text | Small capitals over the group. |
| `layout` | text | `list` (default): each drink with its category, name, `details` and `servedWith`. `inline`: the names in one line. |

The staff page shows every drink of the groups in one list: category, name,
`servedWith`, `staff.bottles`, `staff.serving` and the swaps.

### Example

The food of `examples/data`, one section of two parts (a field or two left
out):

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
    { "type": "sets", "items": ["fish", "meat"], "note": "Your waiter will take your choice after the starters." },
    {
      "type": "text",
      "id": "allergy-card",
      "audience": "guest",
      "variant": "card",
      "text": "Something you do not eat? Just tell your waiter: the kitchen will adjust the dishes."
    }
  ]
}
```

## guests.json

An array of records: a guest record per page, and one staff record.

```json
[
  { "token": "egret-xnmg", "name": "Greta", "seats": [{ "number": 19 }, { "number": 1, "plusOne": true, "name": "Hugo" }] },
  { "token": "plover-32fe", "name": "Peggy and Walter", "seats": [{ "number": 2, "name": "Peggy" }, { "number": 3, "name": "Walter", "requirements": ["vegan"] }] },
  { "token": "DmFnSjs_glP7Qu8z8_MRKw", "staff": true }
]
```

### Guest records

| Field | Type | Meaning |
|---|---|---|
| `token` | text, required | The secret name of the page's directory. See [Tokens](#tokens). |
| `name` | text, required | Who the page is for: "Greta", "Peggy and Walter". `links` prints it. |
| `seats` | array, required | One to three seats, the guest's own seat first. |
| `sections` | object | Changes to the sections for this page. See [Section overrides](#section-overrides). |

A record is a page, not a person: a couple may share one record and one page,
with a seat each.

### Seats

| Field | Type | Meaning |
|---|---|---|
| `number` | number, required | A seat of the table; without a table, 1 to 999. |
| `name` | text | Who sits there. Required on every seat after the first, unless it is a +1. |
| `plusOne` | boolean | The seat of a companion: `true` on any seat but the first. |
| `requirements` | array | Requirement ids: badges on the staff plan, pills in the seat table. |

A seat can be taken once: not by two records, not by a host, not when it is
reserved. A +1 seat that is not next to its guest's own seat on the plan gets
a warning (the numbers go round the table: the last seat and seat 1 meet).

The guest page shows the names of the record's seats and nothing about
anybody else. The staff seat table shows a +1 with whose guest it is: "Hugo ·
Greta’s guest", or "+1 · Greta’s guest, [name]" without a name.

At most three seats: a guest's plan marks each seat in a colour of its own.
Split a larger party into several records.

### Section overrides

`sections` of a record changes the sections of its own page, by section id.
A record such as this one, made up for the example, shows the hidden toasts,
adds a note to the closing section and hides the allergy card (in
`examples/data`, Frida, Ingrid and Otis each use one of these):

```json
{
  "token": "Nora-k8tm",
  "name": "Nora",
  "seats": [{ "number": 5 }],
  "sections": {
    "toasts": { "visible": true },
    "signature": { "note": "Thank you for coming all the way from the coast!" },
    "food": { "widgets": { "allergy-card": { "visible": false } } }
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `visible` | boolean | Shows a hidden section, or hides a shown one, on this page. |
| `note` | text, several lines | A personal note in a card at the end of the section. |
| `widgets` | object | Widget id → `{ "visible": true }` or `{ "visible": false }`. |

The cover, staff-only sections and staff-only widgets cannot be overridden: a
guest never sees them. A note on a section hidden for the guest gets a
warning. The staff page never shows a guest's note.

### The staff record

```json
{ "token": "DmFnSjs_glP7Qu8z8_MRKw", "staff": true }
```

A token and `"staff": true`, nothing else; at most one. Its page is the staff
page: every seat, every name, every dietary need, the swaps, the drinks with
their bottles and the staff texts. Without a staff record no staff page is
built, and `validate` warns.

The staff page shows everybody's data, so its token should be fully random:
`python3 build.py token` makes one. A staff token shorter than 16 characters
gets a warning.

### Tokens

A token is the name of its page's directory, and the only thing that keeps
the page from being guessed:

- 5 to 200 characters of A-Z, a-z, 0-9, `_` and `-`;
- unique among the records, letter case aside (they become directory names);
- not `assets`, the directory of the shared files.

`python3 build.py token --prefix Greta` makes a readable token with a random
tail, `Greta-x7kq`. No page holds a token, not even its own: the address is
the only place it appears.
