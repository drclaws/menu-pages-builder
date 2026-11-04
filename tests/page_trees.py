"""Hand-written page trees for the template and fragment tests.

A page tree is what the template and the fragments read: one tree per page,
a guest page or the staff page.  Every contract field always exists - an
empty string, `[]`, `False`, `0` or `None` stands for a missing value - and
a fragment reads nothing else.

`NODES` is that contract: the fields of every node kind.  `CHILDREN` names
the kind of node below a field (one object, or a list of objects); the
other fields hold strings, numbers, flags or lists of strings.  `node()`
refuses a node whose fields are not exactly those of its kind, so a tree here
cannot drift from the contract.

The data is fictional and follows the page design: Ivan & Vera's dinner at
a bistro, an L-shaped table of sixteen seats.  Only one tree has the
navigation bar (`nav`): the others render as pages without it.
The trees:

* `guest_plus_one` - Olga with her +1 at seats 8 and 9, in two colours on the
  table plan and named in the same colours under it; the +1 has no name
  ("your guest");
* `guest_alone` - Boris alone at seat 3: his seat on the plan with the label
  "You", one set;
* `guest_without_table` - Klara at seat 1 of a menu without a table, with
  three sets and one line of drinks;
* `guest_pair` - Peggy and Victor, one record with two named seats, one set;
  the menu has a table, but the widget shows no plan (the scheme is `None`:
  the page reads the same without a drawing);
* `guest_parts` - Nina with her +1 Oscar at seats 15 and 16, both named in
  the seating card, which has no plan: the food in one section of two parts
  under their headings (the set cards under the second one a level lower), a
  section of texts under headings, the navigation bar above it all (the
  signature has no link there);
* `staff` - the staff page: the legend, the plan with the couple and the
  dietary note badges, every seat (a free and a reserved one among them,
  a +1 with a name and one without), the swaps, a dish for the staff only,
  the notes for the staff.

A guest's plan has no couple and no seat numbers: those are on the staff
plan alone.
"""

from __future__ import annotations

from typing import Iterator

#: The section and widget types: the file names in fragments/sections/ and
#: fragments/widgets/.
SECTION_TYPES = ("cover", "custom")
WIDGET_TYPES = ("text", "seating", "dishes", "sets", "drinks", "heading")

#: The fields every widget has, whatever its type.
WIDGET_COMMON_FIELDS = ("type", "domId", "labelledBy")

#: The fields of every node kind; a widget's kind is `widget:<type>`.
NODES = {
    "root": ("isStaff", "coupleNames", "event", "assetsPath", "faviconPath", "themeColor",
             "staff", "counters", "nav", "sections"),
    "navItem": ("label", "target"),
    "event": ("title", "when", "place"),
    "staff": ("updated", "contact", "reminder"),
    "counters": ("guests", "notes", "guestsText", "notesText", "tableLabel"),
    "section": ("id", "type", "domId", "titleId", "title", "eyebrow", "note", "widgets"),
    "widget:text": WIDGET_COMMON_FIELDS + ("text", "variant"),
    "widget:seating": WIDGET_COMMON_FIELDS + ("scheme", "names", "legend", "rows", "footnote"),
    "widget:dishes": WIDGET_COMMON_FIELDS + ("title", "items"),
    "widget:sets": WIDGET_COMMON_FIELDS + ("items", "note", "multiple"),
    "widget:drinks": WIDGET_COMMON_FIELDS + ("groups", "list", "note"),
    "widget:heading": WIDGET_COMMON_FIELDS + ("titleId", "title", "eyebrow"),
    "seatName": ("name", "colour"),
    "legend": ("letter", "label"),
    "row": ("number", "name", "isPlusOne", "hostName", "roleLabel", "isCouple", "isFree",
            "tags"),
    "dish": ("name", "ingredients", "allergens", "tags", "noRestrictions", "swapLines", "note"),
    "set": ("id", "domId", "title", "hint", "eyebrow", "courses", "pairing", "swapLines", "nested"),
    "group": ("title", "layout", "joined", "items"),
    "drink": ("category", "name", "line"),
    "scheme": ("width", "height", "hidden", "tableLabel", "total", "mine", "single", "outline",
               "couple", "seats", "badges", "labels"),
    "schemeCouple": ("text", "x", "y", "vertical"),
    "schemeSeat": ("number", "cx", "cy", "r", "kind", "mark", "colour", "ring", "ringR"),
    "schemeBadge": ("letter", "cx", "cy", "r"),
    "schemeLabel": ("x", "y", "anchor"),
}

#: (kind, field) -> the kind of the node below the field, or of every node in
#: the list there.  `widget` stands for each node's `widget:<type>`.
CHILDREN = {
    ("root", "event"): "event",
    ("root", "staff"): "staff",
    ("root", "counters"): "counters",
    ("root", "nav"): "navItem",
    ("root", "sections"): "section",
    ("section", "widgets"): "widget",
    ("widget:seating", "scheme"): "scheme",
    ("widget:seating", "names"): "seatName",
    ("widget:seating", "legend"): "legend",
    ("widget:seating", "rows"): "row",
    ("widget:dishes", "items"): "dish",
    ("widget:sets", "items"): "set",
    ("set", "courses"): "dish",
    ("widget:drinks", "groups"): "group",
    ("widget:drinks", "list"): "drink",
    ("group", "items"): "drink",
    ("scheme", "couple"): "schemeCouple",
    ("scheme", "seats"): "schemeSeat",
    ("scheme", "badges"): "schemeBadge",
    ("scheme", "labels"): "schemeLabel",
}

#: Checked enumerations: the only fields a class modifier may come from.
ENUMS = {
    "variant": ("body", "lead", "card", "signature"),
    "layout": ("list", "inline"),
    "kind": ("regular", "couple", "you"),
    "mark": ("none", "flagged"),
    "colour": ("1", "2", "3"),
    "anchor": ("start", "end", "middle"),
}


def node_kind(kind: str, value: dict) -> str:
    """The kind of a node: a widget is `widget:<type>`."""
    return f"widget:{value['type']}" if kind == "widget" else kind


def node(kind: str, /, **values) -> dict:
    """A node of `kind` with exactly the contract fields, in their order.

    `kind` is positional only: a scheme seat has a field of that name.
    """
    fields = NODES[node_kind(kind, values)]
    missing = sorted(set(fields) - set(values))
    extra = sorted(set(values) - set(fields))
    if missing or extra:
        raise ValueError(f"a {kind} node: missing {missing}, extra {extra}")
    return {field: values[field] for field in fields}


def nodes(tree: dict, kind: str = "root") -> Iterator[tuple[str, dict]]:
    """(kind, node) of `tree` and of every node below it, depth first."""
    kind = node_kind(kind, tree)
    yield kind, tree
    for field, value in tree.items():
        child = CHILDREN.get((kind, field))
        if child is None or value is None:
            continue
        for item in value if isinstance(value, list) else [value]:
            yield from nodes(item, child)


# --- the page and its parts --------------------------------------------------

COUPLE = "Ivan & Vera"
EVENT = {"title": "Anniversary dinner", "when": "15 June 2030, 19:00",
         "place": "Riverside Bistro · Example Street 5"}
ASSETS = "/assets"


def root(*, staff_page: bool, sections: list, staff: dict | None = None,
         counters: dict | None = None, nav: tuple = ()) -> dict:
    """The root of a page; a guest page leaves the staff fields empty.  `nav`
    is (label, section id) for every link in the navigation bar."""
    return node(
        "root", isStaff=staff_page, coupleNames=COUPLE, event=node("event", **EVENT),
        assetsPath=ASSETS, faviconPath=f"{ASSETS}/favicon.svg", themeColor="#f1f2f4",
        staff=staff or node("staff", updated="", contact="", reminder=""),
        counters=counters or node("counters", guests=0, notes=0, guestsText="", notesText="",
                                  tableLabel=""),
        nav=[node("navItem", label=label, target=f"s-{section_id}") for label, section_id in nav],
        sections=sections,
    )


def cover() -> dict:
    """The cover: it shows the root's fields; its own are empty."""
    return node("section", id="cover", type="cover", domId="s-cover", titleId="s-cover--title",
                title="", eyebrow="", note="", widgets=[])


def section(section_id: str, title: str, eyebrow: str = "", note: str = "",
            widgets: list | None = None) -> dict:
    dom_id = f"s-{section_id}"
    return node("section", id=section_id, type="custom", domId=dom_id,
                titleId=f"{dom_id}--title", title=title, eyebrow=eyebrow, note=note,
                widgets=widgets or [])


def widget(kind: str, section_id: str, number: int, *, labelled_by: str = "", **fields) -> dict:
    """A widget; `number` is its place in the data (hidden ones count as well).
    It is labelled by its section title unless `labelled_by` says otherwise
    (the sets under a part heading)."""
    return node("widget", type=kind, domId=f"s-{section_id}--w{number}",
                labelledBy=labelled_by or f"s-{section_id}--title", **fields)


def heading(section_id: str, number: int, title: str, eyebrow: str = "") -> dict:
    """The heading of a section part."""
    return widget("heading", section_id, number, titleId=f"s-{section_id}--w{number}--title",
                  title=title, eyebrow=eyebrow)


def dish(name: str, ingredients: str = "", *, allergens: tuple = (), tags: str = "",
         no_restrictions: bool = False, swaps: tuple = (), note: str = "") -> dict:
    return node("dish", name=name, ingredients=ingredients, allergens=list(allergens),
                tags=tags, noRestrictions=no_restrictions, swapLines=list(swaps), note=note)


def dishes(entries: tuple, staff_page: bool) -> list[dict]:
    """The dishes of `entries` (name, ingredients, what the staff sees) for a page."""
    return [dish(name, ingredients, **(extra if staff_page else {}))
            for name, ingredients, extra in entries]


def seating(section_id: str, *, scheme: dict | None = None, names: tuple = (),
            legend: tuple = (), rows: tuple = (), footnote: str = "") -> dict:
    """The seating widget; `names` are who sits at the record's seats, in
    order: each takes the colour of its place."""
    return widget("seating", section_id, 1, scheme=scheme,
                  names=[node("seatName", name=name, colour=colour)
                         for name, colour in zip(names, ENUMS["colour"])],
                  legend=[node("legend", letter=letter, label=label) for letter, label in legend],
                  rows=list(rows), footnote=footnote)


def row(number: int, name: str = "", *, plus_one_of: str = "", role: str = "",
        couple: bool = False, free: bool = False, tags: tuple = ()) -> dict:
    return node("row", number=number, name=name, isPlusOne=bool(plus_one_of),
                hostName=plus_one_of, roleLabel=role, isCouple=couple, isFree=free,
                tags=list(tags))


def sets(widget_dom_id: str, entries: tuple, staff_page: bool, nested: bool = False) -> list[dict]:
    """The sets of `entries` for a page; the swaps are for the staff only.
    `nested`: the widget stands under a part heading."""
    return [
        node("set", id=set_id, domId=f"{widget_dom_id}--set-{set_id}", title=title, hint=hint,
             eyebrow=eyebrow, courses=dishes(courses, staff_page), pairing=pairing,
             swapLines=list(swaps) if staff_page else [], nested=nested)
        for set_id, title, hint, eyebrow, courses, pairing, swaps in entries
    ]


def drink(category: str, name: str, line: str = "") -> dict:
    return node("drink", category=category, name=name, line=line)


# --- the dinner menu -----------------------------------------------------------

STARTERS = (
    ("Beetroot tartare", "Beetroot, walnuts, rye crisp",
     {"allergens": ("nuts", "gluten"),
      "swaps": ("Seat 3 — serve the nut-free version on a separate plate",
                "Seat 10 — serve it without the rye crisp")}),
    ("Burrata with tomatoes", "Burrata, heirloom tomatoes, basil",
     {"allergens": ("lactose",),
      "swaps": ("Seats 10 & 14 — serve the tomatoes without burrata",)}),
    ("Grilled vegetables", "Courgette, pepper, herb oil", {"tags": "vegan · gluten-free"}),
    ("Smoked trout on rye", "Trout, rye bread, dill",
     {"allergens": ("gluten",),
      "swaps": ("Seat 10 — serve it on cucumber slices instead of rye",),
      "note": "Keep the dill sauce on the side"}),
    ("Marinated olives", "Olives, lemon, thyme", {"no_restrictions": True}),
)

#: A widget dish for the staff only: guest pages never have it.
ON_REQUEST = (
    ("Mushroom risotto", "Arborio rice, porcini, parmesan",
     {"allergens": ("lactose",), "note": "Only when a guest asks for it"}),
)

SETS = (
    ("a", "Set A", "Fish", "two courses",
     (("Salmon tartare", "Salmon, avocado, crème fraîche", {"allergens": ("lactose",)}),
      ("Sea bass with a pistachio crust", "Sea bass, pistachios, spinach",
       {"allergens": ("nuts",)})),
     "white wine — see Wines",
     ("If chosen by seat 3 (no nuts) — serve the second course without the crust.",
      "By seats 10 & 14 (no lactose) — serve the first course without crème fraîche.")),
    ("b", "Set B", "Meat", "two courses",
     (("Beef carpaccio", "Beef, rocket, croutons", {"allergens": ("gluten",)}),
      ("Lamb with root vegetables", "Lamb, carrot, parsnip, jus", {"no_restrictions": True})),
     "red wine — see Wines",
     ("If chosen by seat 7 (vegan) — serve the vegan version: roasted roots with lentils.",
      "By seat 10 (no gluten) — serve the first course without croutons.")),
)

#: The starters of a menu without a table, under a list title.
PLAIN_STARTERS = (
    ("Sourdough and butter", "Sourdough bread, salted butter", {}),
    ("Garden salad", "Leaves, radish, lemon dressing", {}),
)

#: The sets of a menu without a table: one course each, some without a hint,
#: an eyebrow or a pairing.
PLAIN_SETS = (
    ("one", "Set 1", "Fish", "one course",
     (("Baked cod", "Cod, new potatoes, dill", {}),), "white wine", ()),
    ("two", "Set 2", "Meat", "",
     (("Roast chicken", "Chicken, thyme, carrots", {}),), "", ()),
    ("three", "Set 3", "", "",
     (("Barley and mushroom stew", "Pearl barley, mushrooms, parsley", {}),), "", ()),
)

LEGEND = (("N", "no nuts"), ("G", "no gluten"), ("L", "no lactose"), ("V", "vegan"),
          ("A", "no alcohol"))

ALLERGY_NOTE = ("Allergies or intolerances? Just tell your waiter — the kitchen will adjust "
                "the dishes.")
SOFT_DRINKS = "Still and sparkling water, lemonade, apple juice, tea and coffee"


def guest_drinks(section_id: str, number: int) -> dict:
    """A guest's drinks: one line of soft drinks, a list of wines, a note."""
    return widget("drinks", section_id, number, groups=[
        node("group", title="Soft drinks", layout="inline", joined=SOFT_DRINKS, items=[]),
        node("group", title="Wines", layout="list", joined="", items=[
            drink("Sparkling", "Example Brut, Riverside Cellars",
                  "Example Valley · Chardonnay · with the starters"),
            drink("White", "Example White, Hillside Estate",
                  "Example Coast · Sauvignon Blanc · with Set A"),
            drink("Red", "Example Red, Old Mill Winery",
                  "Example Hills · Pinot Noir · with Set B"),
        ]),
    ], list=[], note="Cocktails on request — just ask at the bar.")


def staff_drinks(section_id: str, number: int) -> dict:
    """The drinks on the staff page: one list, what to serve and when."""
    return widget("drinks", section_id, number, groups=[], list=[
        drink("Sparkling", "Example Brut, Riverside Cellars",
              "with the starters · 6 bottles · from 19:00, well chilled · seat 1 — no alcohol"),
        drink("White", "Example White, Hillside Estate", "with Set A · 4 bottles · 8–10 °C"),
        drink("Red", "Example Red, Old Mill Winery", "with Set B · 4 bottles · open by 18:30"),
        drink("Soft", SOFT_DRINKS,
              "water on the table from the start; tea and coffee after the main course"),
    ], note="Cocktails only on request; the bar has the list.")


def signature(note: str = "") -> dict:
    """The closing section of a guest page: the couple's names."""
    return section("signature", "Enjoy the evening!", note=note, widgets=[
        widget("text", "signature", 1, text=COUPLE, variant="signature"),
    ])


# --- the table plan --------------------------------------------------------------

TABLE_LABEL = "L-shaped table"
#: The outline of the two arms and the centres of the sixteen seats, in
#: units of the 318 x 310 field, as the geometry lays out the table.
TABLE_OUTLINE = ("M50 60L230 60A10 10 0 0 1 240 70L240 250A10 10 0 0 1 230 260L198 260"
                 "A10 10 0 0 1 188 250L188 112L50 112A10 10 0 0 1 40 102L40 70"
                 "A10 10 0 0 1 50 60Z")
SEAT_CENTRES = ((18, 86), (56, 38), (98, 38), (140, 38), (182, 38), (224, 38), (262, 97),
                (262, 139), (262, 181), (262, 223), (214, 282), (166, 218), (166, 176),
                (145, 134), (103, 134), (61, 134))
COUPLE_SEATS = (4, 5)
#: The couple label inside the top arm: the names in capitals, as the build
#: writes them.
COUPLE_LABEL = COUPLE.replace("&", "·").upper()


def scheme(*, staff_page: bool, own: tuple = (), mine: str = "", flagged: tuple = (),
           badges: tuple = (), label: tuple = ()) -> dict:
    """The L-shaped table plan for a page, every number a string.

    `own` are the guest's seats in record order (each takes the colour of
    its place), `flagged` the seats with a dietary note; `badges` are
    (letter, cx, cy), `label` the (x, y, anchor) of "You".  The staff plan
    has the couple, a guest's plan does not.
    """
    colours = dict(zip(own, ENUMS["colour"]))
    seats = []
    for number, (cx, cy) in enumerate(SEAT_CENTRES, start=1):
        couple = staff_page and number in COUPLE_SEATS
        kind = "you" if number in own else "couple" if couple else "regular"
        mark = "flagged" if number in flagged else "none"
        radius = "16.25" if kind == "you" else "13.75" if mark == "flagged" else "14.25"
        seats.append(node("schemeSeat", number=str(number), cx=str(cx), cy=str(cy), r=radius,
                          kind=kind, mark=mark, colour=colours.get(number, ""),
                          ring=kind == "you", ringR="21"))
    return node(
        "scheme", width="318", height="310", hidden=staff_page, tableLabel=TABLE_LABEL,
        total=str(len(SEAT_CENTRES)), mine=mine, single=len(own) == 1, outline=TABLE_OUTLINE,
        couple=node("schemeCouple", text=COUPLE_LABEL, x="114", y="86", vertical=False)
        if staff_page else None,
        seats=seats,
        badges=[node("schemeBadge", letter=letter, cx=str(cx), cy=str(cy), r="9")
                for letter, cx, cy in badges],
        labels=[node("schemeLabel", x=str(x), y=str(y), anchor=anchor)
                for x, y, anchor in ([label] if label else [])],
    )


# --- the trees -------------------------------------------------------------------

def guest_plus_one() -> dict:
    """Olga and her +1 at seats 8 and 9, the whole menu, a note on one section."""
    return root(staff_page=False, sections=[
        cover(),
        section("seats", "Your seats", widgets=[seating(
            "seats",
            scheme=scheme(staff_page=False, own=(8, 9), mine="Olga — blue, your guest — dark red"),
            names=("Olga", "your guest"))]),
        section("starters", "Starters", "Shared plates for the table", widgets=[
            widget("dishes", "starters", 1, title="", items=dishes(STARTERS, False))]),
        section("main", "Main course", "Choose one of two sets", widgets=[
            widget("sets", "main", 1, items=sets("s-main--w1", SETS, False),
                   note="Your waiter will take your choice after the starters.", multiple=True),
            widget("text", "main", 2, text=ALLERGY_NOTE, variant="card"),
        ]),
        section("drinks", "Drinks", widgets=[guest_drinks("drinks", 1)]),
        signature(note="We kept the seats by the window for you."),
    ])


def guest_alone() -> dict:
    """Boris alone at seat 3: the plan with "You" by his seat, one set."""
    return root(staff_page=False, sections=[
        cover(),
        section("seats", "Your seat", widgets=[seating(
            "seats",
            scheme=scheme(staff_page=False, own=(3,), mine="Boris — blue", label=(98, 10, "middle")),
            names=("Boris",))]),
        section("main", "Main course", widgets=[
            widget("sets", "main", 1, items=sets("s-main--w1", SETS[1:], False), note="",
                   multiple=False)]),
        signature(),
    ])


def guest_without_table() -> dict:
    """Klara at seat 1 of a menu without a table: no scheme, a titled list of
    starters, three sets."""
    return root(staff_page=False, sections=[
        cover(),
        section("welcome", "Welcome", widgets=[
            widget("text", "welcome", 1, text="We are glad to have you with us tonight.",
                   variant="lead"),
            widget("text", "welcome", 2,
                   text="The kitchen closes at 22:00.\nDessert is served at the bar.",
                   variant="body"),
        ]),
        section("seats", "Your seat", widgets=[seating(
            "seats", names=("Klara",))]),
        section("starters", "Starters", widgets=[
            widget("dishes", "starters", 1, title="For the table",
                   items=dishes(PLAIN_STARTERS, False))]),
        section("main", "Main course", "Choose one of three sets", widgets=[
            widget("sets", "main", 1, items=sets("s-main--w1", PLAIN_SETS, False), note="",
                   multiple=True)]),
        section("drinks", "Drinks", widgets=[widget("drinks", "drinks", 1, groups=[
            node("group", title="", layout="inline", joined="Water, lemonade, tea and coffee",
                 items=[])], list=[], note="")]),
    ])


def guest_pair() -> dict:
    """Peggy and Victor: one record, two named seats, a menu with one set."""
    return root(staff_page=False, sections=[
        cover(),
        section("seats", "Your seats", widgets=[seating(
            "seats", names=("Peggy", "Victor"))]),
        section("main", "Main course", widgets=[
            widget("sets", "main", 1, items=sets("s-main--w1", SETS[:1], False), note="",
                   multiple=False)]),
        signature(),
    ])


#: The texts of the short-notes section: (heading, text).
INFO = (("Smoking", "Smoking is fine on the terrace by the river."),
        ("Instant camera", "An instant camera waits at the bar: take a picture and leave it for "
                           "the couple."))


def guest_parts() -> dict:
    """Nina and her +1 Oscar: the food in two parts, short notes under headings."""
    info = []
    for number, (title, text) in enumerate(INFO):
        info += [heading("info", 2 * number + 1, title),
                 widget("text", "info", 2 * number + 2, text=text, variant="body")]
    nav = (("Seats", "seats"), ("Food", "food"), ("Drinks", "drinks"), ("Info", "info"))
    return root(staff_page=False, nav=nav, sections=[
        cover(),
        section("seats", "Your seats", widgets=[seating(
            "seats", names=("Nina", "Oscar"))]),
        section("food", "Food", widgets=[
            heading("food", 1, "Starters", "Shared plates for the table"),
            widget("dishes", "food", 2, title="", items=dishes(STARTERS[:3], False)),
            # the dishes on request (3) are for the staff only
            heading("food", 4, "Main course", "Choose one of two sets"),
            widget("sets", "food", 5, labelled_by="s-food--w4--title",
                   items=sets("s-food--w5", SETS, False, nested=True),
                   note="Your waiter will take your choice after the starters.", multiple=True),
            widget("text", "food", 6, text=ALLERGY_NOTE, variant="card"),
        ]),
        section("drinks", "Drinks", widgets=[guest_drinks("drinks", 1)]),
        section("info", "Good to know", widgets=info),
        signature(),
    ])


def staff() -> dict:
    """The staff page: every seat and need, the swaps and the notes for the staff."""
    rows = (
        row(1, "Alyona", tags=("no alcohol",)),
        row(2, free=True),
        row(3, "Boris", tags=("no nuts",)),
        row(4, "Vera", role="bride", couple=True),
        row(5, "Ivan", role="groom", couple=True),
        row(6, "Gleb"),
        row(7, "Zhanna", tags=("vegan",)),
        row(8, "Olga"),
        row(9, plus_one_of="Olga"),
        row(10, "Egor", tags=("no gluten", "no lactose")),
        row(11, free=True),  # reserved: free on purpose, the same on the page
        row(12, "Peggy"),
        row(13, "Victor"),
        row(14, "Marta", tags=("no lactose",)),
        row(15, "Nina"),
        row(16, "Oscar", plus_one_of="Nina"),
    )
    return root(
        staff_page=True,
        staff=node("staff", updated="10 June 2030", contact="Selma (planner) · +00 000 000 00 00",
                   reminder="Staff link only — please do not show this page to guests.\n\n"
                            "Print it on the morning of the dinner."),
        counters=node("counters", guests=14, notes=5, guestsText="14 guests",
                      notesText="5 dietary notes", tableLabel=TABLE_LABEL),
        sections=[
            cover(),
            section("seats", "Seating and dietary notes", widgets=[seating(
                "seats",
                scheme=scheme(staff_page=True, flagged=(1, 3, 7, 10, 14),
                              badges=(("A", 30, 74), ("N", 110, 26), ("V", 274, 85),
                                      ("G", 250, 211), ("L", 274, 211), ("L", 157, 122))),
                legend=LEGEND, rows=rows,
                footnote="Main course: every guest picks Set A or Set B at the table — take "
                         "the orders after the starters are served.")]),
            section("starters", "Starters", "Shared plates · on the table by 19:15", widgets=[
                widget("dishes", "starters", 1, title="", items=dishes(STARTERS, True)),
                widget("dishes", "starters", 2, title="On request",
                       items=dishes(ON_REQUEST, True)),
            ]),
            section("main", "Main course", "Two sets · guests choose at the table", widgets=[
                widget("sets", "main", 1, items=sets("s-main--w1", SETS, True),
                       note="The kitchen needs every order by 20:00.", multiple=True)]),
            section("drinks", "Drinks", "What to serve and when",
                    widgets=[staff_drinks("drinks", 2)]),
        ],
    )


#: The trees by name; the names also name the rendered page directories.
TREES = {
    "guest-plus-one": guest_plus_one,
    "guest-alone": guest_alone,
    "guest-without-table": guest_without_table,
    "guest-pair": guest_pair,
    "guest-parts": guest_parts,
    "staff": staff,
}


def all_trees() -> dict[str, dict]:
    """A fresh copy of every tree, by name."""
    return {name: build() for name, build in TREES.items()}
