# Languages

The pages hold two kinds of text. Everything that comes from the data (dish
names, section titles, notes) is written in the data, in any language. The
words of the pages themselves (the page title, the labels of the seat table,
"Paired with", "14 guests") are English by default, and `menu.json` can
replace them with two fields:

| Field | Type | Rules |
|---|---|---|
| `lang` | text | A language tag: `en`, `de`, `en-GB`, `sr-Latn`. Default `en`. It becomes the `lang` attribute of every page and chooses the plural rule. |
| `strings` | object | The words of the pages, by key (see [Keys](#keys)). |

For an English menu (`lang` left out, or a tag of the language `en`),
`strings` is optional and may give any of the keys: the others keep their
English defaults. For any other language, `strings` must give **every** key,
and `validate` lists the missing ones as an error. A page in two languages is
a defect.

Dates are free text: `event.when` and `staff.updated` are shown as written,
so the data writes them in its own language. The build formats no date and
ships no locale data.

## Keys

There are four kinds of words:

- a **text** is one line;
- a **pattern** is one line with placeholders in braces, each of them
  required, and no other placeholder;
- a **plural** is an object with a form per plural category, each form with
  the placeholder `{n}` (see [Plural forms](#plural-forms));
- `seatColours` is a list of three names, one per seat colour.

| Key | Kind | English default | Where it appears |
|---|---|---|---|
| `pageTitle` | text | `Dinner menu` | The page title, before the names in `coupleNames`. |
| `staffVersion` | text | `Staff version · not for guests` | The bar at the top of the staff page. |
| `updated` | pattern `{date}` | `updated {date}` | The staff bar, with `staff.updated`. |
| `contact` | pattern `{contact}` | `Contact on the night: {contact}` | The staff footer, with `staff.contact`. |
| `sections` | text | `Sections` | The label of the navigation bar for screen readers. |
| `tablePlan` | pattern `{table}`, `{seats}`, `{yours}`, `{colours}` | `Table plan: {table}, {seats}. {yours}: {colours}` | The text of a guest's plan for screen readers. |
| `seatCount` | plural | `{n} seat`, `{n} seats` | `{seats}` in `tablePlan`. |
| `you` | text | `You` | The label by the seat of a single-seat record on its plan. |
| `seatNumber` | text | `No.` | The first column of the staff seat table. |
| `guestAndNotes` | text | `Guest · dietary notes` | The second column of the staff seat table. |
| `guestOf` | pattern `{name}` | `{name}’s guest` | Whose guest a +1 is, in the staff seat table. |
| `nameBlank` | text | `[name]` | A +1 without a name, in the staff seat table. |
| `noRestrictions` | text | `no restrictions` | The pill of a dish with no allergens and no tags. |
| `pairedWith` | pattern `{pairing}` | `Paired with {pairing}` | Under a set, with its `pairing`. |
| `seat` | text | `Seat` | Before one seat number: "Seat 4 — …". |
| `seats` | text | `Seats` | Before several: "Seats 7 & 10 — …". |
| `seatInline` | text | `seat` | One seat inside a line: "If chosen by seat 4". |
| `seatsInline` | text | `seats` | Several inside a line: "By seats 10 & 14". |
| `and` | text | `&` | Before the last of several seat numbers. |
| `yourGuest` | text | `your guest` | The name of a +1 without one, on its guest's page. |
| `seatColours` | list of 3 | `blue`, `dark red`, `green` | `{colours}` in `tablePlan`: whose seat has which colour. |
| `swapFirst` | text | `If chosen by` | The first swap line of a set on the staff page. |
| `swapNext` | text | `By` | Each further swap line of the set. |
| `yourSeat` | text | `Your seat` | The default title of the seating section for a single-seat record, and `{yours}` in `tablePlan`. |
| `yourSeats` | text | `Your seats` | The same for a record of several seats. |
| `staffSeating` | text | `Seating and dietary notes` | The default title of the seating section on the staff page. |
| `guestCount` | plural | `{n} guest`, `{n} guests` | The number of taken seats on the staff cover. |
| `noteCount` | plural | `{n} dietary note`, `{n} dietary notes` | The number of seats with a dietary note on the staff cover. |

Some marks are typography, not words, and stay the same in every language:
`, ` between the items of a list, ` — ` between seats and what to do for them,
` · ` between the parts of a line, and the full stop that ends a swap line
written without one.

An unknown key is an error, with a suggestion for a misspelt one ("did you
mean 'sections'?").

## Plural forms

The build knows the plural rules of many languages for whole numbers, after
the rules of Unicode CLDR. The primary subtag of `lang` chooses the rule:
`sr-Latn` uses the rule of `sr`.

| Languages | Forms |
|---|---|
| af, az, bg, ca, da, de, el, en, eo, es, et, eu, fi, fo, fy, gl, hu, it, ka, kk, ky, lb, mn, nb, nl, nn, no, rm, sq, sv, sw, tr, uz | `one` (1), `other` |
| fr, pt | `one` (0 and 1), `other` |
| ru, uk, be | `one` (1, 21, 31…, not 11), `few` (2-4, 22-24…, not 12-14), `many` |
| bs, hr, sr | `one` (1, 21, 31…, not 11), `few` (2-4, 22-24…, not 12-14), `other` |
| pl | `one` (1 only), `few` (2-4, 22-24…, not 12-14), `many` |
| cs, sk | `one` (1), `few` (2-4), `other` |
| sl | `one` (1, 101…), `two` (2, 102…), `few` (3-4, 103-104…), `other` |
| ja, zh, ko, vi, th, id, ms | `other` only |

A plural word must give every form its language uses. The form `other` is
always accepted, and any other category is an error. A language without a
built-in rule uses `one` and `other`, and `validate` warns about it.

## The label of a guest's seat

The word `you` stands by a seat on the plan, and the plan keeps room for it at
every seat. That room is estimated from the length of the word, about 7 px
per character and at least 26 px, since nothing is measured at build time. A
long word may not fit at some seats: `validate` then reports "no room for the
label of the guest's seat" for them. A shorter word, or more room around the
table, solves it.

## Scripts and fonts

- The pages are for **left-to-right scripts**. Right-to-left text is out of
  scope: the table plan is drawn for left-to-right reading.
- There is **no hyphenation**: a long word breaks at the edge of its box
  without a hyphen.
- The pages use the system fonts of the reader's device. They cover Latin
  with diacritics, Cyrillic and Greek on common systems; other scripts rely on
  the platform's fallback fonts.
- Small capitals are upper case by the style sheet, which follows the page's
  `lang`: set the right tag.
- The couple label on the staff plan (`couple.label`) is upper-cased by the
  build, without locale rules (a German "ß" becomes "SS", a Turkish dotted "i"
  becomes a plain "I"). Its width is estimated for Latin capitals, one per
  character: a label of wide letters may need fewer characters than
  `validate` allows before it warns.
- A requirement's badge letter (`requirements.*.letter`) is one capital letter
  of any script: "Č" and "Ž" work.
- Ids and tokens are ASCII: they become HTML ids and directory names, and no
  reader sees them.

## A complete sample: Serbian, Latin script

Every key, for `"lang": "sr-Latn"` (the forms `one`, `few` and `other`).
Copy it into `menu.json` next to `"schemaVersion"`:

```json
{
  "lang": "sr-Latn",
  "strings": {
    "pageTitle": "Jelovnik večere",
    "staffVersion": "Verzija za osoblje · ne za goste",
    "updated": "ažurirano {date}",
    "contact": "Kontakt tokom večeri: {contact}",
    "sections": "Odeljci",
    "tablePlan": "Raspored stola: {table}, {seats}. {yours}: {colours}",
    "seatCount": { "one": "{n} mesto", "few": "{n} mesta", "other": "{n} mesta" },
    "you": "Vi",
    "seatNumber": "Br.",
    "guestAndNotes": "Gost · napomene o ishrani",
    "guestOf": "gost: {name}",
    "nameBlank": "[ime]",
    "noRestrictions": "bez ograničenja",
    "pairedWith": "Uz meni: {pairing}",
    "seat": "Mesto",
    "seats": "Mesta",
    "seatInline": "mesto",
    "seatsInline": "mesta",
    "and": "i",
    "yourGuest": "vaš gost",
    "seatColours": ["plava", "tamnocrvena", "zelena"],
    "swapFirst": "Ako bira",
    "swapNext": "Za",
    "yourSeat": "Vaše mesto",
    "yourSeats": "Vaša mesta",
    "staffSeating": "Raspored sedenja i ishrana",
    "guestCount": { "one": "{n} gost", "few": "{n} gosta", "other": "{n} gostiju" },
    "noteCount": { "one": "{n} napomena o ishrani", "few": "{n} napomene o ishrani", "other": "{n} napomena o ishrani" }
  }
}
```

`guestOf` avoids a possessive: Serbian would decline the name, and
"gost: {name}" keeps it in its basic form.
