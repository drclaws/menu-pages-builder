"""The page template and the fragments against the contract of the page tree.

The trees are written by hand (`tests/page_trees.py`) and built by the data
layer (`menu_tools._page.build_trees`) from the data sets of
`tests/fixtures.py`, so the fragments and the data layer cannot drift apart
unnoticed.  Every node is wrapped in a `Strict` dict, which fails when a
fragment asks for a field that its kind of node does not have, even inside an
`if:`, and which records every field a fragment asks for: a field of the
contract that no fragment reads has to be listed in `UNREAD` with its reason.
The pages are rendered the way the build publishes them (the comments
removed) and go through the checks of a finished HTML page (`check_html`).
"""

from __future__ import annotations

import collections
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core as core  # noqa: E402  (imported after sys.path is prepared)
from menu_tools import _page, _schema  # noqa: E402
from tests import fixtures  # noqa: E402
from tests import page_trees as T  # noqa: E402

TEMPLATE = ROOT / "template.html"
FRAGMENTS_DIR = ROOT / "fragments"
APP_JS = ROOT / "assets" / "app.js"

#: The files of the output a page refers to.
PUBLISHED = frozenset({"assets/app.css", "assets/app.js", "assets/favicon.svg"})

#: The partials: the shared pieces that no value of the data can choose.
PARTIALS = ("dish-item", "legend", "pills", "scheme", "section-head", "section-nav",
            "section-note", "sections", "seat-table")

#: The kinds of node of the plan of the table.
SCHEME_KINDS = ("scheme", "schemeCouple", "schemeSeat", "schemeBadge", "schemeLabel")

#: The fields of the contract that no fragment reads, with the reason.
UNREAD = {
    "section.id": "the id of the data; the page names a section by its domId",
    "set.id": "the id of the data; the page names a set by its domId",
    "sets.count": "the script counts the tabs itself; multiple tells whether there are tabs",
    "seating.mySeats": "the page shows the own seats on the scheme and by the names under it",
    "mySeat.number": "a field of mySeats",
    "mySeat.mark": "a field of mySeats",
}

#: The fields that only the staff page fills: a guest's page has them empty
#: and never reads them.
STAFF_ONLY = frozenset({
    "root.staff", "staff.updated", "staff.contact", "staff.reminder",
    "root.counters", *(f"counters.{field}" for field in T.NODES["counters"]),
    "seating.legend", "seating.rows", "seating.footnote",
    *(f"legend.{field}" for field in T.NODES["legend"]),
    *(f"row.{field}" for field in T.NODES["row"]),
    "scheme.badges", *(f"schemeBadge.{field}" for field in T.NODES["schemeBadge"]),
    "scheme.couple", *(f"schemeCouple.{field}" for field in T.NODES["schemeCouple"]),
    "dish.allergens", "dish.tags", "dish.noRestrictions", "dish.swapLines", "dish.note",
    "set.swapLines", "drinks.list",
})
#: The fields that only a guest's page fills: the staff page has them empty
#: (or has no such widget) and never reads them.
GUEST_ONLY = frozenset({
    "seating.mySeats", *(f"mySeat.{field}" for field in T.NODES["mySeat"]),
    "seating.names", *(f"seatName.{field}" for field in T.NODES["seatName"]),
    "scheme.labels", "scheme.mine", "scheme.single", "schemeSeat.colour",
    *(f"schemeLabel.{field}" for field in T.NODES["schemeLabel"]),
    "drinks.groups", *(f"group.{field}" for field in T.NODES["group"]),
})

#: The words of the interface: they live in the fragments, never in the tree.
STAFF_WORDS = ("Staff version · not for guests", "updated", "No.", "Guest · dietary notes",
               "’s guest", "[name]", "no restrictions", "Contact on the night:")
#: The words of the plan of the table: its name and the label of the guest's seat.
SCHEME_WORDS = ("Table plan", "seats", "Your seat", "Your seats", "You")
#: The classes of the parts that the staff page alone has: the couple and the
#: numbers of the seats among them.
STAFF_CLASSES = ("staff-bar", "staff-footer", "cover--staff", "cover__counters", "legend",
                 "seat-table", "seat-number", "pills", "pill", "dish__line", "sets__swaps",
                 "drinks__staff", "seating__footnote", "seating__divider", "seat-badge",
                 "seat--flagged", "seat--couple", "scheme__couple", "seat__number")
#: The classes that the staff page never has: the guest's own seats, their
#: rings, colours and label, the names under the plan.
GUEST_CLASSES = ("seat--you", "seat__ring", "seat-label", "seating__name",
                 *(f"seat--colour-{colour}" for colour in T.ENUMS["colour"]),
                 *(f"seating__name--colour-{colour}" for colour in T.ENUMS["colour"]))


def field_name(kind: str, field: str) -> str:
    """`<kind>.<field>`; the fields every widget has are `widget.<field>`."""
    if kind.startswith("widget:"):
        return f"widget.{field}" if field in T.WIDGET_COMMON_FIELDS else f"{kind[7:]}.{field}"
    return f"{kind}.{field}"


#: Every field of the contract, by its name.
CONTRACT = frozenset(field_name(kind, field) for kind, fields in T.NODES.items()
                     for field in fields)


class Strict(dict):
    """A node of the page tree that fails on a field outside its kind.

    The template engine looks a field up with `in` before it takes the value,
    so `__contains__` sees every field a fragment asks for and records it.
    """

    def __init__(self, kind: str, values: dict, reads: set[str]):
        super().__init__(values)
        self.kind = kind
        self.reads = reads

    def __contains__(self, key: object) -> bool:
        if not dict.__contains__(self, key):
            raise AssertionError(f"a fragment reads the field {key!r}, "
                                 f"which a {self.kind} node lacks")
        self.reads.add(field_name(self.kind, str(key)))
        return True


def strict(tree: dict, reads: set[str], kind: str = "root") -> Strict:
    """`tree` with every node a `Strict` dict that records into `reads`."""
    kind = T.node_kind(kind, tree)
    values = {}
    for field, value in tree.items():
        child = T.CHILDREN.get((kind, field))
        if child is not None and isinstance(value, list):
            value = [strict(item, reads, child) for item in value]
        elif child is not None and isinstance(value, dict):
            value = strict(value, reads, child)
        values[field] = value
    return Strict(kind, values, reads)


def render_page(tree: dict, template: core.Template | None = None) -> str:
    """The finished page: rendered, comments removed, as the build publishes it."""
    template = template or core.load_template(TEMPLATE)
    return core.strip_html_comments(template.render(tree), TEMPLATE.name)


def render_strict(tree: dict, template: core.Template, reads: set[str] | None = None) -> str:
    """The page of `tree` with every node `Strict`: a variant of a tree reaches
    branches the four trees do not, and a field outside the contract read
    there fails as well."""
    return render_page(strict(tree, set() if reads is None else reads), template)


def html_problems(page: str) -> list[tuple[int, str]]:
    return core.check_html(page, PUBLISHED.__contains__)


def sections_of(tree: dict, section_id: str) -> dict:
    return next(section for section in tree["sections"] if section["id"] == section_id)


def widgets_of(tree: dict, kind: str) -> list[dict]:
    return [widget for section in tree["sections"] for widget in section["widgets"]
            if widget["type"] == kind]


def element(page: str, class_name: str) -> str:
    """The first element with the class, from its start tag to the matching end tag."""
    start = re.search(r'<(\w+)\b[^>]*\sclass="(?:[^"]* )?%s(?: [^"]*)?"' % re.escape(class_name),
                      page)
    assert start, class_name
    tag, depth, position = start.group(1), 0, start.start()
    for match in re.finditer(r"<(/?)%s\b[^>]*>" % tag, page[position:]):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return page[position:position + match.end()]
    raise AssertionError(f"no end of {class_name}")


def visible_text(markup: str) -> str:
    """The text of the markup, tags dropped and white space collapsed."""
    text = re.sub(r"<[^>]+>", " ", markup)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return " ".join(text.split())


class Outline(HTMLParser):
    """Ids, references, headings, hidden elements and reveal marks of a page."""

    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                      "meta", "source", "track", "wbr"})

    def __init__(self, document: str):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.headings: list[int] = []
        self.hidden: list[tuple[str, dict]] = []
        self.reveals: list[tuple[str, dict]] = []
        self.nested_reveals = 0
        self.scripts: list[dict] = []
        self.styles: list[str] = []
        self.open: list[tuple[str, bool]] = []
        self.feed(document)
        self.close()

    def element(self, tag: str, attrs: list[tuple[str, str | None]], void: bool) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if "id" in attributes:
            self.ids.append(attributes["id"])
        for name in ("aria-labelledby", "aria-controls", "aria-describedby"):
            for target in attributes.get(name, "").split():
                self.references.append((name, target))
        if attributes.get("href", "").startswith("#"):
            self.references.append(("href", attributes["href"][1:]))
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if "hidden" in attributes:
            self.hidden.append((tag, attributes))
        if tag == "script":
            self.scripts.append(attributes)
        self.styles += [name for name in attributes if name == "style" or name.startswith("on")]
        reveal = "data-reveal" in attributes
        if reveal:
            self.reveals.append((tag, attributes))
            if any(marked for _tag, marked in self.open):
                self.nested_reveals += 1
        if not void:
            self.open.append((tag, reveal))

    def handle_starttag(self, tag, attrs):
        self.element(tag, attrs, tag in self.VOID)

    def handle_startendtag(self, tag, attrs):
        self.element(tag, attrs, True)

    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                del self.open[index:]
                break


def tabs_hooks() -> list[str]:
    """The data attributes the tabs module of the script looks for."""
    source = APP_JS.read_text(encoding="utf-8")
    module = source[source.index("Module tabs"):source.index("Module reveal")]
    hooks = re.findall(r"'\[(data-[a-z-]+)\]'", module)
    assert hooks, "no hooks in the tabs module"
    return sorted(set(hooks))


def section_nav_hooks() -> list[str]:
    """The data attributes the sectionNav module of the script looks for."""
    source = APP_JS.read_text(encoding="utf-8")
    module = source[source.index("Module sectionNav"):]
    hooks = re.findall(r"'\[(data-[a-z-]+)\]'", module)
    assert hooks, "no hooks in the sectionNav module"
    return sorted(set(hooks))


# --- the trees and the files ---------------------------------------------------

class TreeTests(unittest.TestCase):
    def test_every_node_has_exactly_the_fields_of_its_kind(self):
        seen = set()
        for name, tree in T.all_trees().items():
            for kind, value in T.nodes(tree):
                seen.add(kind)
                with self.subTest(tree=name, node=kind):
                    self.assertEqual(list(value), list(T.NODES[kind]))
        # every kind of node is in a tree, the plan of the table too
        self.assertEqual(seen, set(T.NODES))
        # the plan of a guest of one seat has the label, the staff plan the
        # badges and the couple, the plan of a guest of two seats none of them
        cases = (("guest-alone", {"schemeLabel"}), ("guest-plus-one", set()),
                 ("staff", {"schemeBadge", "schemeCouple"}))
        for name, kinds in cases:
            with self.subTest(tree=name):
                found = {kind for kind, _value in T.nodes(T.all_trees()[name])}
                self.assertEqual(found & {"schemeLabel", "schemeBadge", "schemeCouple"}, kinds)

    def test_a_node_outside_the_contract_is_refused(self):
        with self.assertRaises(ValueError):
            T.node("drink", category="Red", name="Example Red")
        with self.assertRaises(ValueError):
            T.node("drink", category="Red", name="Example Red", line="", price="")

    def test_the_trees_cover_the_cases(self):
        trees = T.all_trees()
        plus_one = widgets_of(trees["guest-plus-one"], "seating")[0]
        self.assertEqual([(seat["number"], seat["mark"]) for seat in plus_one["mySeats"]],
                         [(8, "you"), (9, "plusOne")])
        marks = {seat["mark"] for tree in trees.values() for widget in widgets_of(tree, "seating")
                 for seat in widget["mySeats"]}
        self.assertEqual(marks, set(T.MY_SEAT_MARKS))
        # the plan of the guest: the own seats in two colours, no couple, no label
        plan = plus_one["scheme"]
        self.assertIsNone(plan["couple"])
        self.assertNotIn("couple", {seat["kind"] for seat in plan["seats"]})
        self.assertEqual([(seat["number"], seat["ring"], seat["colour"]) for seat in plan["seats"]
                          if seat["kind"] == "you"], [("8", True, "1"), ("9", True, "2")])
        self.assertEqual((plan["labels"], plan["single"], plan["badges"]), ([], False, []))
        self.assertEqual(plan["mine"], "Olga — blue, your guest — dark red")
        self.assertEqual([(item["name"], item["colour"]) for item in plus_one["names"]],
                         [("Olga", "1"), ("your guest", "2")])
        # a guest of one seat: "You" by the seat
        alone = widgets_of(trees["guest-alone"], "seating")[0]
        self.assertEqual((alone["scheme"]["single"], len(alone["scheme"]["labels"])), (True, 1))
        self.assertEqual([(item["name"], item["colour"]) for item in alone["names"]], [("Boris", "1")])
        no_table = widgets_of(trees["guest-without-table"], "seating")[0]
        self.assertEqual((no_table["names"][0]["name"], no_table["scheme"]), ("Klara", None))
        # a menu with a table whose widget shows no plan
        pair = widgets_of(trees["guest-pair"], "seating")[0]
        self.assertIsNone(pair["scheme"])
        self.assertEqual([item["name"] for item in pair["names"]], ["Peggy", "Victor"])
        self.assertEqual(len(widgets_of(trees["guest-pair"], "sets")[0]["items"]), 1)
        # the staff plan: the couple label and seats, the flagged seats, a
        # seat with two badges, no labels
        staff_plan = widgets_of(trees["staff"], "seating")[0]["scheme"]
        self.assertEqual(staff_plan["couple"]["text"], T.COUPLE_LABEL)
        self.assertEqual([seat["number"] for seat in staff_plan["seats"] if seat["kind"] == "couple"],
                         ["4", "5"])
        flagged = [seat["number"] for seat in staff_plan["seats"] if seat["mark"] == "flagged"]
        self.assertEqual(flagged, ["1", "3", "7", "10", "14"])
        # a badge sits 12 units off the centre of its seat along x and y
        per_seat = collections.Counter(
            seat["number"] for seat in staff_plan["seats"] for badge in staff_plan["badges"]
            if {abs(int(badge["cx"]) - int(seat["cx"])), abs(int(badge["cy"]) - int(seat["cy"]))}
            == {12})
        self.assertEqual(per_seat, {"1": 1, "3": 1, "7": 1, "10": 2, "14": 1})
        self.assertEqual((staff_plan["hidden"], staff_plan["labels"]), (True, []))
        rows = widgets_of(trees["staff"], "seating")[0]["rows"]
        self.assertEqual(len([row for row in rows if row["isFree"]]), 2)
        self.assertEqual(len([row for row in rows if row["isCouple"]]), 2)
        self.assertEqual(sorted(row["name"] for row in rows if row["isPlusOne"]), ["", "Oscar"])
        self.assertTrue(widgets_of(trees["staff"], "seating")[0]["legend"])
        titles = [widget["title"] for widget in widgets_of(trees["staff"], "dishes")]
        self.assertEqual(titles, ["", "On request"])
        # the title of a list is for both audiences
        titles = [widget["title"] for widget in widgets_of(trees["guest-without-table"], "dishes")]
        self.assertEqual(titles, ["For the table"])
        self.assertTrue(widgets_of(trees["guest-plus-one"], "drinks")[0]["note"])
        self.assertTrue(widgets_of(trees["staff"], "drinks")[0]["note"])
        self.assertTrue(widgets_of(trees["staff"], "sets")[0]["note"])
        # the parts of a section: headings with and without an eyebrow, the
        # set cards under a heading a level lower, labelled by the heading
        headings = widgets_of(trees["guest-parts"], "heading")
        self.assertEqual([(item["title"], bool(item["eyebrow"])) for item in headings],
                         [("Starters", True), ("Main course", True), ("Smoking", False),
                          ("Instant camera", False)])
        self.assertEqual([item["titleId"] for item in headings],
                         [f"{item['domId']}--title" for item in headings])
        nested = widgets_of(trees["guest-parts"], "sets")[0]
        self.assertEqual(nested["labelledBy"], "s-food--w4--title")
        self.assertEqual({item["nested"] for item in nested["items"]}, {True})
        self.assertEqual({item["nested"] for name, tree in trees.items() if name != "guest-parts"
                          for widget in widgets_of(tree, "sets") for item in widget["items"]}, {False})
        variants = {widget["variant"] for tree in trees.values()
                    for widget in widgets_of(tree, "text")}
        self.assertEqual(variants, set(T.ENUMS["variant"]))
        layouts = {group["layout"] for tree in trees.values()
                   for widget in widgets_of(tree, "drinks") for group in widget["groups"]}
        self.assertEqual(layouts, set(T.ENUMS["layout"]))

    def test_the_staff_page_has_its_texts_and_counters(self):
        for name, tree in T.all_trees().items():
            with self.subTest(tree=name):
                self.assertEqual(name == "staff", tree["isStaff"])
        staff = T.staff()
        self.assertTrue(all(staff["staff"].values()))
        self.assertTrue(all(staff["counters"].values()))

    def test_the_fields_of_the_other_audience_are_empty(self):
        def empty(value) -> bool:
            if isinstance(value, dict):
                return all(empty(item) for item in value.values())
            return not value

        for name, tree in T.all_trees().items():
            other = GUEST_ONLY if tree["isStaff"] else STAFF_ONLY
            for kind, value in T.nodes(tree):
                for field, item in value.items():
                    if field_name(kind, field) in other:
                        with self.subTest(tree=name, field=field_name(kind, field)):
                            self.assertTrue(empty(item))


class FragmentFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {path.relative_to(FRAGMENTS_DIR).with_suffix("").as_posix():
                       path.read_text(encoding="utf-8")
                       for path in sorted(FRAGMENTS_DIR.rglob("*.html"))}

    def test_the_files_are_the_types_and_the_partials(self):
        fragments = core.load_fragments(FRAGMENTS_DIR)
        self.assertEqual(T.SECTION_TYPES, _schema.SECTION_TYPES)
        self.assertEqual(T.WIDGET_TYPES, _schema.WIDGET_TYPES)
        self.assertEqual(fragments.names("sections"), sorted(T.SECTION_TYPES))
        self.assertEqual(fragments.names("widgets"), sorted(T.WIDGET_TYPES))
        self.assertEqual(fragments.names("partials"), sorted(PARTIALS))
        self.assertEqual(len(fragments), len(T.SECTION_TYPES) + len(T.WIDGET_TYPES)
                         + len(PARTIALS))

    def test_every_fragment_starts_with_its_contract(self):
        for name, source in self.sources.items():
            with self.subTest(fragment=name):
                self.assertTrue(source.startswith("<!-- "), "no contract comment")
                self.assertIn("expects in ", source[:source.index("-->")])

    def test_the_contract_comments_name_only_fields_of_the_contract(self):
        # every name in camel case is a field (the plain words may be prose)
        fields = {field for names in T.NODES.values() for field in names}
        named = set()
        for name, source in self.sources.items():
            comment = source[:source.index("-->")]
            listed = comment[comment.index("expects in "):].split(". ", 1)[0]
            for word in re.findall(r"\b[a-z]+[A-Z][A-Za-z]*\b", listed):
                named.add(word)
                with self.subTest(fragment=name, field=word):
                    self.assertIn(word, fields)
        self.assertLessEqual({"domId", "titleId", "isStaff", "tableLabel", "swapLines"}, named)

    def test_class_modifiers_come_only_from_checked_enumerations(self):
        for name, source in self.sources.items():
            for classes in re.findall(r'class="([^"]*)"', source):
                for field in re.findall(r"\{\{\s*([^}]*?)\s*\}\}", classes):
                    with self.subTest(fragment=name, field=field):
                        self.assertTrue(field.startswith("."), field)
                        self.assertIn(field[1:], T.ENUMS)

    def test_ids_are_dom_ids_of_the_tree_with_fixed_suffixes(self):
        for name, source in self.sources.items():
            for value in re.findall(r'\sid="([^"]*)"', source):
                with self.subTest(fragment=name, id=value):
                    self.assertRegex(value, r"^\{\{\.(domId|titleId)\}\}(--title|--tab)?$")

    def test_the_reveal_mark_is_in_the_frame_of_a_section_on_the_guest_page_only(self):
        marked = {name: source.count("data-reveal") for name, source in self.sources.items()
                  if "data-reveal" in source}
        self.assertEqual(marked, {"sections/custom": 1})
        self.assertIn('<!-- if:!isStaff --><div class="container" data-reveal><!-- endif -->'
                      '<!-- if:isStaff --><div class="container"><!-- endif -->',
                      self.sources["sections/custom"])
        self.assertNotIn("data-reveal", TEMPLATE.read_text(encoding="utf-8"))

    def test_the_only_links_lead_to_the_sections_of_the_page(self):
        # the pages lead nowhere else: the other addresses are the shared
        # files in <head>; the line of the sections links the parts of the page
        sources = dict(self.sources, template=TEMPLATE.read_text(encoding="utf-8"))
        expected = {"template": ["{{faviconPath}}", "{{assetsPath}}/app.css", "{{assetsPath}}/app.js"],
                    "partials/section-nav": ["#{{.target}}"]}
        for name, source in sources.items():
            markup = re.sub(r"<!--.*?-->", "", source, flags=re.S)
            with self.subTest(file=name):
                self.assertNotRegex(markup, r"(?i)<area[\s/>]")
                links = re.findall(r"(?i)<a[\s/>][^>]*>", markup)
                self.assertEqual(links, ['<a class="section-nav__link" href="#{{.target}}" data-section-nav-link>']
                                 if name == "partials/section-nav" else [])
                addresses = re.findall(r'(?i)\b(?:href|src)\s*=\s*"([^"]*)"', markup)
                self.assertEqual(addresses, expected.get(name, []))
        # the template includes the line only when there is something to link
        self.assertIn("<!-- endif --><!-- if:nav --><!-- include:partials/section-nav --><!-- endif -->\n"
                      '<main class="page">', sources["template"])

    def test_no_styles_or_inline_scripts_in_the_markup(self):
        sources = dict(self.sources, template=TEMPLATE.read_text(encoding="utf-8"))
        for name, source in sources.items():
            markup = re.sub(r"<!--.*?-->", "", source, flags=re.S)
            with self.subTest(file=name):
                self.assertNotRegex(markup, r"<[a-zA-Z][^>]*\sstyle\s*=")
                self.assertNotRegex(markup, r"(?i)<style[\s>]")
                self.assertNotRegex(markup, r"<[a-zA-Z][^>]*\son[a-z]+\s*=")
                scripts = re.findall(r"(?i)<script\b[^>]*>.*?</script>", markup, re.S)
                expected = ['<script src="{{assetsPath}}/app.js" defer></script>'] \
                    if name == "template" else []
                self.assertEqual(scripts, expected)

    def test_the_words_of_the_interface_are_in_the_fragments(self):
        markup = "".join(re.sub(r"<!--.*?-->", "", source, flags=re.S)
                         for source in self.sources.values())
        markup += TEMPLATE.read_text(encoding="utf-8")
        for word in STAFF_WORDS + SCHEME_WORDS + ("Paired with", "—", "Dinner menu · ", 'aria-label="Sections"'):
            with self.subTest(word=word):
                self.assertIn(word, markup)
        # the words of the plan are in its partial: the tree holds none of them
        scheme = re.sub(r"<!--.*?-->", "", self.sources["partials/scheme"], flags=re.S)
        for word in SCHEME_WORDS:
            with self.subTest(word=word):
                self.assertIn(word, scheme)

    def test_the_scheme_partial_draws_the_plan_from_the_contract(self):
        frame = "<!-- with:scheme --><!-- include:partials/scheme --><!-- endwith -->"
        template = core.parse_template(frame, "frame", core.load_fragments(FRAGMENTS_DIR))
        scheme_fields = {field_name(kind, field) for kind in SCHEME_KINDS
                         for field in T.NODES[kind]}
        every = set()
        for name, other in (("guest-plus-one", STAFF_ONLY), ("guest-alone", STAFF_ONLY), ("staff", GUEST_ONLY)):
            tree = T.all_trees()[name]
            reads: set[str] = set()
            scheme = strict(widgets_of(tree, "seating")[0]["scheme"], reads, "scheme")
            output = core.strip_html_comments(
                template.render({"isStaff": tree["isStaff"], "scheme": scheme}), "frame")
            with self.subTest(tree=name):
                self.assertTrue(output.startswith('\n<svg class="scheme" viewBox="0 0 318 310"'))
                self.assertTrue(output.endswith("</svg>\n"))
                self.assertEqual(output.count("<svg"), 1)
                # it reads the fields of the plan alone, of its own audience
                self.assertLessEqual(reads, scheme_fields)
                self.assertEqual(reads & other, set())
            every |= reads
        self.assertEqual(every, scheme_fields)


# --- the contract ---------------------------------------------------------------

class ContractTests(unittest.TestCase):
    """Every field a fragment reads is in the contract; every one is read."""

    @classmethod
    def setUpClass(cls):
        cls.template = core.load_template(TEMPLATE)
        cls.page_reads: dict[str, set[str]] = {name: set() for name in T.TREES}
        cls.pages = {name: render_page(strict(tree, cls.page_reads[name]), cls.template)
                     for name, tree in T.all_trees().items()}
        cls.reads = set().union(*cls.page_reads.values())

    def test_the_trees_render(self):
        self.assertEqual(set(self.pages), set(T.TREES))
        for name, page in self.pages.items():
            with self.subTest(tree=name):
                self.assertTrue(page.startswith("<!doctype html>\n<html lang=\"en\""))

    def test_a_field_outside_the_contract_fails(self):
        for build, kind, field in ((T.guest_plus_one, "section", "eyebrow"),
                                   (T.guest_plus_one, "dish", "ingredients"),
                                   (T.guest_plus_one, "set", "hint"),
                                   (T.staff, "row", "isFree"),
                                   (T.staff, "dish", "swapLines"),
                                   (T.staff, "root", "counters")):
            tree = build()
            victims = [value for node_kind, value in T.nodes(tree) if node_kind == kind]
            del victims[-1][field]
            with self.subTest(kind=kind, field=field), self.assertRaises(AssertionError):
                render_page(strict(tree, set()), self.template)

    def test_every_field_of_the_contract_is_read_or_listed(self):
        self.assertLessEqual(set(UNREAD), CONTRACT)
        self.assertLessEqual(self.reads, CONTRACT)
        self.assertEqual(self.reads & set(UNREAD), set())
        self.assertEqual(CONTRACT - self.reads, set(UNREAD))
        for field, reason in UNREAD.items():
            with self.subTest(field=field):
                self.assertTrue(reason)

    def test_each_page_reads_the_fields_of_its_audience_only(self):
        # a staff field read on a guest's page would show the staff part as
        # soon as the data layer filled it there by mistake, and the other way
        self.assertLessEqual(STAFF_ONLY | GUEST_ONLY, CONTRACT)
        self.assertEqual(STAFF_ONLY & GUEST_ONLY, frozenset())
        for name, reads in self.page_reads.items():
            other = GUEST_ONLY if name == "staff" else STAFF_ONLY
            with self.subTest(page=name):
                self.assertEqual(reads & other, set())
        # and each page does read the fields of its own audience
        self.assertLessEqual(STAFF_ONLY, self.page_reads["staff"])
        guests = set().union(*(reads for name, reads in self.page_reads.items()
                               if name != "staff"))
        self.assertEqual(GUEST_ONLY - guests, GUEST_ONLY & set(UNREAD))


# --- the pages --------------------------------------------------------------------

class PageTests(unittest.TestCase):
    """The pages of the hand-made trees, as the build would publish them."""

    @classmethod
    def setUpClass(cls):
        cls.template = core.load_template(TEMPLATE)
        cls.trees = T.all_trees()
        cls.pages = {name: render_strict(tree, cls.template) for name, tree in cls.trees.items()}

    def guest_pages(self):
        return {name: page for name, page in self.pages.items() if name != "staff"}

    def test_the_pages_pass_the_checks_of_the_build(self):
        for name, page in self.pages.items():
            with self.subTest(page=name):
                core.check_rendered(page)
                self.assertEqual(html_problems(page), [])

    def test_no_styles_and_no_inline_scripts(self):
        for name, page in self.pages.items():
            outline = Outline(page)
            with self.subTest(page=name):
                self.assertEqual(outline.styles, [])
                self.assertNotRegex(page, r"(?i)<style[\s>]")
                self.assertEqual(outline.scripts, [{"src": "/assets/app.js", "defer": ""}])
                self.assertRegex(page, r'<script src="/assets/app.js" defer></script>')

    def test_ids_are_unique_and_every_reference_resolves(self):
        for name, page in self.pages.items():
            outline = Outline(page)
            with self.subTest(page=name):
                repeated = [value for value, count in collections.Counter(outline.ids).items()
                            if count > 1]
                self.assertEqual(repeated, [])
                self.assertTrue(all(outline.ids))
                dangling = [(attribute, target) for attribute, target in outline.references
                            if target not in outline.ids]
                self.assertEqual(dangling, [])

    def test_the_heading_outline_has_no_gaps(self):
        for name, page in self.pages.items():
            levels = Outline(page).headings
            with self.subTest(page=name, levels=levels):
                self.assertEqual(levels[0], 1)
                self.assertEqual(levels.count(1), 1)
                for previous, level in zip(levels, levels[1:]):
                    self.assertLessEqual(level, previous + 1)
                self.assertIn(3, levels)  # the sets

    def test_the_reveal_mark_is_on_the_guest_page_alone(self):
        for name, page in self.pages.items():
            outline = Outline(page)
            custom = [section for section in self.trees[name]["sections"]
                      if section["type"] == "custom"]
            with self.subTest(page=name):
                if name == "staff":
                    self.assertEqual(outline.reveals, [])
                    continue
                self.assertEqual(len(outline.reveals), len(custom))
                self.assertEqual(outline.nested_reveals, 0)
                for tag, attributes in outline.reveals:
                    self.assertEqual((tag, attributes["class"]), ("div", "container"))

    def test_everything_is_visible_without_the_script(self):
        for name, page in self.pages.items():
            hidden = Outline(page).hidden
            with self.subTest(page=name):
                for _tag, attributes in hidden:
                    self.assertIn("data-tabs-tablist", attributes)

    def test_the_head_of_the_page(self):
        for name, page in self.pages.items():
            head = page[:page.index("</head>")]
            audience = "staff" if name == "staff" else "guest"
            with self.subTest(page=name):
                self.assertTrue(page.startswith(
                    f'<!doctype html>\n<html lang="en" class="menu menu--{audience}">\n<head>'))
                for tag in ('<meta charset="utf-8">',
                            '<meta name="viewport" content="width=device-width, initial-scale=1, '
                            'viewport-fit=cover">',
                            '<meta name="color-scheme" content="only light">',
                            '<meta name="theme-color" content="#f1f2f4">',
                            '<meta name="text-scale" content="scale">',
                            '<meta name="referrer" content="no-referrer">',
                            '<meta name="robots" content="noindex, nofollow">',
                            "<title>Dinner menu · Ivan &amp; Vera</title>",
                            '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">',
                            '<link rel="stylesheet" href="/assets/app.css">'):
                    self.assertIn(tag, head)
                # no link preview: no Open Graph, no cards, no description
                self.assertNotRegex(head, r'property="og:|name="twitter:|name="description"')
                self.assertEqual(page.count("<html"), 1)

    def test_the_staff_bar_and_footer(self):
        page = self.pages["staff"]
        bar = element(page, "staff-bar")
        self.assertTrue(page.index("<body>") < page.index(bar) < page.index("<main"))
        self.assertEqual(visible_text(bar), "Staff version · not for guests updated 10 June 2030")
        footer = element(page, "page-footer")
        self.assertGreater(page.index(footer), page.index("</main>"))
        self.assertEqual(
            re.findall(r"<p[^>]*>(.*?)</p>", footer),
            ["Contact on the night: Selma (planner) · +00 000 000 00 00",
             "Staff link only — please do not show this page to guests.",
             "Print it on the morning of the dinner."])
        self.assertNotIn("<a ", footer)  # the phone is text, not a link

    def test_the_staff_frame_without_some_of_its_texts(self):
        def page(**staff):
            tree = T.staff()
            tree["staff"].update(staff)
            reads: set[str] = set()
            document = render_strict(tree, self.template, reads)
            self.assertEqual(reads & GUEST_ONLY, set())
            self.assertEqual(html_problems(document), [])
            return document

        no_contact = page(contact="")
        self.assertNotIn("Contact on the night", no_contact)
        self.assertIn("Print it on the morning of the dinner.", element(no_contact, "page-footer"))
        nothing = page(contact="", reminder="")
        self.assertNotIn("page-footer", nothing)
        self.assertNotIn("staff-footer", nothing)
        no_reminder = page(reminder="")
        self.assertEqual(len(re.findall(r"<p", element(no_reminder, "staff-footer"))), 1)
        undated = page(updated="")
        self.assertEqual(visible_text(element(undated, "staff-bar")),
                         "Staff version · not for guests")

    def test_the_line_of_the_sections(self):
        page = self.pages["guest-parts"]
        line = element(page, "section-nav")
        # the first element of the body of a guest page, right before main
        self.assertTrue(page[page.index("<body>"):].replace("<body>", "", 1).lstrip().startswith(line))
        self.assertTrue(page.index(line) < page.index('<main class="page">'))
        self.assertEqual(line,
                         '<nav class="section-nav" aria-label="Sections" data-section-nav>\n'
                         '  <div class="container section-nav__inner">\n'
                         '    <ul class="section-nav__list" role="list" data-section-nav-list>\n'
                         '      <li class="section-nav__item"><a class="section-nav__link" href="#s-seats" '
                         'data-section-nav-link>Seats</a></li>\n'
                         '      <li class="section-nav__item"><a class="section-nav__link" href="#s-food" '
                         'data-section-nav-link>Food</a></li>\n'
                         '      <li class="section-nav__item"><a class="section-nav__link" href="#s-drinks" '
                         'data-section-nav-link>Drinks</a></li>\n'
                         '      <li class="section-nav__item"><a class="section-nav__link" href="#s-info" '
                         'data-section-nav-link>Info</a></li>\n'
                         "    </ul>\n  </div>\n</nav>")
        # every link leads to a section of the page; the signature has none
        ids = Outline(page).ids
        targets = re.findall(r'href="#([^"]+)"', line)
        self.assertTrue(set(targets) <= set(ids))
        self.assertNotIn("s-signature", targets)
        self.assertIn("s-signature", ids)
        # the hooks of the script are those of the markup
        self.assertEqual(section_nav_hooks(), ["data-section-nav", "data-section-nav-link",
                                               "data-section-nav-list"])
        for hook in section_nav_hooks():
            self.assertIn(f" {hook}>", line)

    def test_a_page_without_a_label_has_no_line(self):
        # nothing of the line, not even an empty line of text
        for name, page in self.pages.items():
            if name == "guest-parts":
                continue
            with self.subTest(page=name):
                self.assertNotIn("section-nav", page)
                self.assertNotIn("<nav", page)
                if name == "staff":
                    self.assertIn('</header>\n\n<main class="page">', page)
                else:
                    self.assertIn('<body>\n\n\n\n<main class="page">', page)

    def test_the_line_of_the_staff_page_follows_the_staff_bar(self):
        tree = T.staff()
        tree["nav"] = [T.node("navItem", label=label, target=f"s-{section_id}")
                       for label, section_id in (("Seats", "seats"), ("Starters", "starters"),
                                                 ("Main course", "main"), ("Drinks", "drinks"))]
        page = render_strict(tree, self.template)
        self.assertEqual(html_problems(page), [])
        bar, line = element(page, "staff-bar"), element(page, "section-nav")
        self.assertTrue(page.index(bar) < page.index(line) < page.index('<main class="page">'))
        self.assertEqual(re.findall(r'href="#([^"]+)" data-section-nav-link>([^<]*)</a>', line),
                         [("s-seats", "Seats"), ("s-starters", "Starters"), ("s-main", "Main course"),
                          ("s-drinks", "Drinks")])
        self.assertEqual([target for name, target in Outline(page).references
                          if name == "href" and target not in Outline(page).ids], [])

    def test_a_guest_page_has_no_staff_parts(self):
        for name, page in self.guest_pages().items():
            classes = {value for found in re.findall(r'class="([^"]*)"', page)
                       for value in found.split()}
            with self.subTest(page=name):
                self.assertEqual(classes & set(STAFF_CLASSES), set())
                for word in STAFF_WORDS:
                    self.assertNotIn(word, visible_text(page))
                self.assertNotIn("<table", page)
                self.assertNotIn("<footer", page)

    def test_the_staff_page_has_no_parts_of_a_guest(self):
        page = self.pages["staff"]
        classes = {value for found in re.findall(r'class="([^"]*)"', page)
                   for value in found.split()}
        self.assertEqual(classes & set(GUEST_CLASSES), set())
        self.assertNotIn('role="img"', page)
        self.assertNotIn("Table plan", page)
        self.assertNotIn("seating__meta", page)

    def test_the_modifiers_are_the_enumerations(self):
        everything = "".join(self.pages.values())
        for variant in T.ENUMS["variant"]:
            self.assertIn(f"text-widget--{variant}", everything)
        for layout in T.ENUMS["layout"]:
            self.assertIn(f"drinks__group--{layout}", everything)

    def test_values_are_escaped(self):
        tree = T.guest_plus_one()
        widgets_of(tree, "seating")[0]["names"][0]["name"] = "Olga <b>& co</b> {{x}}"
        widgets_of(tree, "dishes")[0]["items"][0]["name"] = "<script>alert(1)</script>"
        page = render_strict(tree, self.template)
        self.assertIn("Olga &lt;b&gt;&amp; co&lt;/b&gt; &#123;&#123;x&#125;&#125;", page)
        self.assertNotIn("<b>", page)
        self.assertNotIn("<script>alert", page)
        core.check_rendered(page)
        self.assertEqual(html_problems(page), [])


class WidgetTests(unittest.TestCase):
    """What each section and widget shows to the guest and to the staff."""

    @classmethod
    def setUpClass(cls):
        cls.template = core.load_template(TEMPLATE)
        cls.pages = {name: render_strict(tree, cls.template)
                     for name, tree in T.all_trees().items()}

    def section(self, page: str, section_id: str) -> str:
        found = re.search(r'<section class="[^"]*" id="s-%s".*?</section>' % section_id,
                          self.pages[page], re.S)
        self.assertIsNotNone(found, section_id)
        return found.group(0)

    def test_the_cover_of_a_guest(self):
        cover = self.section("guest-plus-one", "cover")
        self.assertIn('<p class="section__subtitle cover__eyebrow">Ivan &amp; Vera</p>', cover)
        self.assertIn('<h1 class="cover__title" id="s-cover--title">Wedding dinner</h1>', cover)
        self.assertIn('<hr class="divider divider--accent cover__divider">', cover)
        self.assertIn('<p class="cover__when">15 June 2030, 19:00</p>', cover)
        self.assertIn('<p class="cover__place">Riverside Bistro · Example Street 5</p>', cover)
        self.assertNotIn("cover--staff", cover)

    def test_the_header_of_the_staff_page(self):
        cover = self.section("staff", "cover")
        self.assertIn('<section class="cover cover--staff" id="s-cover"', cover)
        self.assertIn(">Ivan &amp; Vera · Wedding dinner</p>", cover)
        self.assertIn('<h1 class="cover__title" id="s-cover--title">15 June 2030, 19:00</h1>',
                      cover)
        self.assertEqual(re.findall(r'<li class="(pill[^"]*)">([^<]*)</li>', cover),
                         [("pill pill--plain", "14 guests"),
                          ("pill pill--plain", "L-shaped table"),
                          ("pill pill--flag", "5 dietary notes")])
        self.assertNotIn("divider", cover)

    def test_the_counters_show_only_what_there_is(self):
        tree = T.staff()
        tree["counters"].update(notes=0, notesText="", tableLabel="")
        cover = re.search(r'<section class="cover.*?</section>',
                          render_strict(tree, self.template), re.S).group(0)
        self.assertEqual(re.findall(r'<li class="pill[^"]*">([^<]*)</li>', cover), ["14 guests"])

    def test_the_seats_of_a_guest(self):
        # a name per seat in the colour of the seat, in the order of the
        # record; no number of a seat anywhere in the section
        cases = {"guest-plus-one": ("Olga", "your guest"),
                 "guest-alone": ("Boris",),
                 "guest-without-table": ("Klara",),
                 "guest-pair": ("Peggy", "Victor"),
                 "guest-parts": ("Nina", "Oscar")}
        for name, names in cases.items():
            section = self.section(name, "seats")
            with self.subTest(page=name):
                labels = "".join(f' <span class="time-label time-label--strong seating__name '
                                 f'seating__name--colour-{colour}">{who}</span>'
                                 for who, colour in zip(names, T.ENUMS["colour"]))
                self.assertIn(f'<p class="seating__meta">{labels}</p>', section)
                self.assertIn('<div class="card seating__card">', section)
                for part in ("legend", "seat-table", "seating__footnote", "<hr", "seat__number",
                             "seating__seats", "seating__who"):
                    self.assertNotIn(part, section)
                self.assertNotRegex(visible_text(section), r"\d")

    def test_the_legend_and_the_seat_table(self):
        section = self.section("staff", "seats")
        legend = element(section, "legend")
        self.assertEqual(re.findall(r'<span class="legend__mark" aria-hidden="true">(\w)</span>'
                                    r'<span class="legend__label">([^<]*)</span>', legend),
                         list(T.LEGEND))
        self.assertLess(section.index(legend), section.index("seating__card"))
        table = element(section, "seat-table")
        self.assertIn('<th class="seat-table__no" scope="col">No.</th>'
                      '<th scope="col">Guest · dietary notes</th>', table)
        rows = re.findall(r"<tr>\s*<td.*?</tr>", table, re.S)
        self.assertEqual(len(rows), 16)
        text = [visible_text(row) for row in rows]
        self.assertEqual(text[0], "1 Alyona no alcohol")
        self.assertEqual(text[1], "2 —")
        self.assertEqual(text[3], "4 Vera · bride")
        self.assertEqual(text[8], "9 +1 · Olga’s guest, [name]")
        self.assertEqual(text[9], "10 Egor no gluten no lactose")
        self.assertEqual(text[10], "11 —")
        # a +1 with a name: the name in bold, as every guest, and no "+1"
        self.assertEqual(text[15], "16 Oscar · Nina’s guest")
        self.assertIn('<span class="seat-table__name">Oscar</span>\n'
                      '        <span class="seat-table__role">· Nina’s guest</span>', rows[15])
        self.assertIn('<span class="seat-table__name">+1</span>', rows[8])
        self.assertIn('<span class="seat-number seat-number--couple">4</span>', rows[3])
        self.assertIn('<span class="seat-number">3</span>', rows[2])
        self.assertEqual(re.findall(r'<li class="pill pill--flag">([^<]*)</li>', rows[9]),
                         ["no gluten", "no lactose"])
        self.assertNotIn("pills", rows[5])
        self.assertIn('<p class="note-line seating__footnote">Main course:', section)
        # a rule parts the table from the plan above it
        self.assertEqual(section.count('<hr class="divider seating__divider">'), 1)

    def test_the_plan_stands_first_in_the_card_of_the_seats(self):
        start = '<div class="card seating__card">\n    \n<svg class="scheme"'
        guest = element(self.section("guest-plus-one", "seats"), "seating__card")
        self.assertTrue(guest.startswith(start))
        self.assertLess(guest.index("</svg>"), guest.index('<p class="seating__meta">'))
        self.assertIn('role="img" aria-label="Table plan: L-shaped table, 16 seats. Your seats: '
                      'Olga — blue, your guest — dark red"', guest)
        alone = element(self.section("guest-alone", "seats"), "seating__card")
        self.assertIn('role="img" aria-label="Table plan: L-shaped table, 16 seats. Your seat: '
                      'Boris — blue"', alone)
        self.assertIn('<text class="seat-label seat-label--middle" x="98" y="10">You</text>', alone)
        staff = element(self.section("staff", "seats"), "seating__card")
        self.assertTrue(staff.startswith(start))
        order = [staff.index(marker) for marker in ('aria-hidden="true"', "</svg>",
                                                   '<hr class="divider seating__divider">',
                                                   '<table class="seat-table">',
                                                   "seating__footnote")]
        self.assertEqual(order, sorted(order))
        # without a plan: no drawing and no rule above the table
        for name in ("guest-pair", "guest-without-table"):
            with self.subTest(page=name):
                self.assertNotIn("<svg", self.pages[name])
        tree = T.staff()
        widgets_of(tree, "seating")[0]["scheme"] = None
        page = render_strict(tree, self.template)
        self.assertEqual(html_problems(page), [])
        self.assertNotIn("<svg", page)
        self.assertNotIn("seating__divider", page)

    def test_the_dishes_of_a_guest(self):
        section = self.section("guest-plus-one", "starters")
        items = re.findall(r'<li class="dish">(.*?)</li>', section, re.S)
        self.assertEqual(len(items), len(T.STARTERS))
        self.assertEqual(re.findall(r"<p [^>]*>([^<]*)</p>", items[0]),
                         ["Beetroot tartare", "Beetroot, walnuts, rye crisp"])
        self.assertNotIn("dishes__title", section)
        # the title of a list is not a staff part: a guest's list may have one
        titled = self.section("guest-without-table", "starters")
        self.assertRegex(titled, r'<div class="widget dishes-widget" id="s-starters--w1">\s*'
                                 r'<p class="dishes__title">For the table</p>\s*'
                                 r'<ul class="dishes" role="list">')
        self.assertNotIn("pills", titled)

    def test_the_dishes_of_the_staff(self):
        section = self.section("staff", "starters")
        lists = re.findall(r'<div class="widget dishes-widget".*?</ul>\s*</div>', section, re.S)
        self.assertEqual(len(lists), 2)
        items = re.findall(r'<li class="dish">(.*?)\n</li>', lists[0], re.S)
        self.assertEqual(len(items), len(T.STARTERS))
        self.assertEqual(visible_text(items[0]),
                         "Beetroot tartare nuts gluten Seat 3 — serve the nut-free version on a "
                         "separate plate Seat 10 — serve it without the rye crisp")
        self.assertIn('<li class="pill pill--flag">nuts</li><li class="pill pill--flag">gluten'
                      '</li>', items[0])
        self.assertIn('<ul class="pills" role="list"><li class="pill">vegan · gluten-free</li>'
                      '</ul>', items[2])
        self.assertIn('<p class="note-line dish__line">Keep the dill sauce on the side</p>',
                      items[3])
        self.assertIn('<li class="pill">no restrictions</li>', items[4])
        self.assertNotIn("dish__ingredients", section)
        self.assertIn('<p class="dishes__title">On request</p>', lists[1])
        self.assertIn("Mushroom risotto", lists[1])

    def test_a_dish_without_allergen_information(self):
        tree = T.staff()
        widgets_of(tree, "dishes")[0]["items"][0].update(allergens=[], swapLines=[])
        page = render_strict(tree, self.template)
        # an empty row, which the style sheet hides (.pills:empty)
        self.assertRegex(page, r'<p class="dish__name">Beetroot tartare</p>\s*'
                               r'<ul class="pills" role="list"></ul>\s*</li>')

    def test_the_sets_carry_the_hooks_of_the_script(self):
        hooks = tabs_hooks()
        self.assertEqual(hooks, ["data-tabs", "data-tabs-panel", "data-tabs-tab",
                                 "data-tabs-tablist"])
        for name in ("guest-plus-one", "guest-without-table", "staff"):
            widget = element(self.pages[name], "sets-widget")
            with self.subTest(page=name):
                for hook in hooks:
                    self.assertIn(hook, widget)
                self.assertRegex(widget, r'^<div class="widget sets-widget sets" id="[\w-]+" '
                                         r'data-tabs>')
                tablist = re.search(r"<div [^>]*data-tabs-tablist[^>]*>", widget).group(0)
                self.assertIn(' role="tablist" aria-labelledby="s-main--title"', tablist)
                self.assertTrue(tablist.endswith(" hidden>"))
                tabs = re.findall(r"<button [^>]*data-tabs-tab>", widget)
                panels = re.findall(r"<article [^>]*data-tabs-panel>", widget)
                self.assertEqual(len(tabs), len(panels))
                self.assertGreaterEqual(len(tabs), 2)
                for tab, panel in zip(tabs, panels):
                    panel_id = re.search(r' id="([^"]+)"', panel).group(1)
                    self.assertIn(f'id="{panel_id}--tab" aria-controls="{panel_id}"', tab)
                    self.assertIn(' role="tab" ', tab)
                    self.assertIn(' aria-selected="false" tabindex="-1" ', tab)
                    self.assertIn(f'aria-labelledby="{panel_id}--title"', panel)
                    self.assertNotIn("hidden", panel)

    def test_the_heading_of_a_part(self):
        food = self.section("guest-parts", "food")
        self.assertIn('<header class="widget heading-widget" id="s-food--w1">\n'
                      '  <h3 class="heading-widget__title" id="s-food--w1--title">Starters</h3>\n'
                      '  <p class="section__subtitle heading-widget__eyebrow">Shared plates for the table'
                      '</p>\n</header>', food)
        order = [food.index(marker) for marker in ('id="s-food--title"', 'id="s-food--w1--title"',
                                                   'id="s-food--w2"', 'id="s-food--w4--title"',
                                                   'id="s-food--w5"', "text-widget--card")]
        self.assertEqual(order, sorted(order))
        # a heading without an eyebrow is the title alone
        info = self.section("guest-parts", "info")
        self.assertIn('<header class="widget heading-widget" id="s-info--w1">\n'
                      '  <h3 class="heading-widget__title" id="s-info--w1--title">Smoking</h3>\n'
                      "</header>", info)
        self.assertNotIn("heading-widget__eyebrow", info)

    def test_a_set_under_the_heading_of_a_part(self):
        widget = element(self.pages["guest-parts"], "sets-widget")
        self.assertEqual(re.findall(r"<(h\d) class=\"sets__title\" id=\"([^\"]+)\">", widget),
                         [("h4", "s-food--w5--set-a--title"), ("h4", "s-food--w5--set-b--title")])
        self.assertNotIn("<h3", widget)
        # the tab list is named by the heading of the part
        tablist = re.search(r"<div [^>]*data-tabs-tablist[^>]*>", widget).group(0)
        self.assertIn(' role="tablist" aria-labelledby="s-food--w4--title"', tablist)
        # outside a part a card has the h3 it always had
        for name in ("guest-plus-one", "guest-without-table", "guest-pair", "staff"):
            with self.subTest(page=name):
                self.assertNotIn('<h4 class="sets__title"', self.pages[name])
                self.assertIn('<h3 class="sets__title" id="s-main--w1--set-', self.pages[name])
        # the staff page with the same parts
        tree = T.staff()
        main = sections_of(tree, "main")
        main["widgets"] = [T.heading("main", 1, "Main course", "Two sets · guests choose at the table"),
                           T.widget("sets", "main", 2, labelled_by="s-main--w1--title",
                                    items=T.sets("s-main--w2", T.SETS, True, nested=True),
                                    note="", count=2, multiple=True)]
        page = render_strict(tree, self.template)
        self.assertEqual(html_problems(page), [])
        staff = element(page, "sets-widget")
        self.assertEqual(len(re.findall(r'<h4 class="sets__title"', staff)), 2)
        self.assertIn('aria-labelledby="s-main--w1--title"', staff)
        self.assertEqual(Outline(page).headings.count(4), 2)

    def test_a_single_set_has_no_tabs(self):
        widget = element(self.pages["guest-pair"], "sets-widget")
        self.assertIn("data-tabs-panel", widget)
        for part in ("data-tabs-tablist", "data-tabs-tab", 'role="tab'):
            self.assertNotIn(part, widget)

    def test_the_card_of_a_set(self):
        guest = element(self.pages["guest-plus-one"], "sets-widget")
        panel = re.search(r"<article .*?</article>", guest, re.S).group(0)
        order = ['<h3 class="sets__title" id="s-main--w1--set-a--title">Set A</h3>',
                 '<p class="sets__eyebrow">two courses</p>', '<ol class="dishes sets__courses"',
                 "Salmon tartare", "Sea bass with a pistachio crust",
                 '<p class="note-line sets__pairing">Paired with white wine — see Wines</p>']
        positions = [panel.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("sets__swaps", guest)
        self.assertTrue(guest.rstrip().endswith(
            '<p class="note-line sets__note">Your waiter will take your choice after the '
            "starters.</p>\n</div>"))
        staff = element(self.pages["staff"], "sets-widget")
        swaps = re.findall(r'<div class="sets__swaps">(.*?)</div>', staff, re.S)
        self.assertEqual(len(swaps), 2)
        self.assertEqual([visible_text(line) for line in
                          re.findall(r'<p class="note-line">([^<]*)</p>', swaps[0])],
                         list(T.SETS[0][6]))
        self.assertIn('<li class="pill pill--flag">lactose</li>', staff)
        self.assertIn("The kitchen needs every order by 20:00.", staff)

    def test_a_set_without_a_hint_an_eyebrow_or_a_pairing(self):
        widget = element(self.pages["guest-without-table"], "sets-widget")
        self.assertEqual(widget.count("sets__tab-hint"), 1 + 1)
        self.assertEqual(widget.count("sets__eyebrow"), 1)
        self.assertEqual(widget.count("sets__pairing"), 1)
        self.assertNotIn("sets__note", widget)

    def test_the_drinks_of_a_guest(self):
        widget = element(self.pages["guest-plus-one"], "drinks-widget")
        groups = re.findall(r'<div class="drinks__group drinks__group--(\w+)">(.*?)\n  </div>',
                            widget, re.S)
        self.assertEqual([layout for layout, _markup in groups], ["inline", "list"])
        self.assertEqual(visible_text(groups[0][1]), f"Soft drinks {T.SOFT_DRINKS}")
        self.assertNotIn("drinks__list", groups[0][1])
        drinks = re.findall(r'<li class="drink">(.*?)</li>', groups[1][1])
        self.assertEqual(len(drinks), 3)
        self.assertEqual(visible_text(drinks[0]), "Sparkling Example Brut, Riverside Cellars "
                                                  "Example Valley · Chardonnay · with the starters")
        self.assertNotIn("schedule", widget)
        self.assertTrue(widget.rstrip().endswith(
            '<p class="note-line drinks__note">Cocktails on request — just ask at the bar.</p>'
            "\n</div>"))
        untitled = element(self.pages["guest-without-table"], "drinks-widget")
        self.assertNotIn("drinks__title", untitled)
        self.assertNotIn("drinks__note", untitled)

    def test_the_drinks_of_the_staff(self):
        widget = element(self.pages["staff"], "drinks-widget")
        self.assertNotIn("drinks__group", widget)
        self.assertIn('<div class="schedule schedule--ruled drinks__staff">', widget)
        items = re.findall(r'<li class="schedule__item">(.*?)</li>', widget, re.S)
        self.assertEqual(len(items), 4)
        self.assertIn('<span class="time-label schedule__time">Sparkling</span>', items[0])
        self.assertIn("seat 1 — no alcohol", items[0])
        self.assertIn("Cocktails only on request; the bar has the list.", widget)

    def test_the_text_widgets(self):
        welcome = self.section("guest-without-table", "welcome")
        self.assertIn('<div class="widget text-widget text-widget--lead prose">', welcome)
        self.assertIn("<p>The kitchen closes at 22:00.<br>Dessert is served at the bar.</p>",
                      welcome)
        main = self.section("guest-plus-one", "main")
        self.assertIn('<div class="widget text-widget text-widget--card prose">\n  <p>Allergies',
                      main)
        signature = self.section("guest-plus-one", "signature")
        self.assertIn('<div class="widget text-widget text-widget--signature prose">\n  '
                      "<p>Ivan &amp; Vera</p>", signature)
        self.assertIn('<div class="card section__note">', signature)
        self.assertLess(signature.index("text-widget--signature"), signature.index("section__note"))
        self.assertEqual(signature.count('class="widget '), 1)

    def test_the_head_of_a_section(self):
        starters = self.section("guest-plus-one", "starters")
        self.assertIn('<header class="section__head">\n  <h2 class="section__title" '
                      'id="s-starters--title">Starters</h2>\n  <p class="section__subtitle">'
                      "Shared plates for the table</p>\n</header>", starters)
        seats = self.section("guest-plus-one", "seats")
        self.assertNotIn("section__subtitle", seats)
        self.assertIn('<h2 class="section__title" id="s-seats--title">Your seats</h2>', seats)


# --- the trees of the data layer ---------------------------------------------------

def strings(value) -> list[str]:
    """Every string of a tree, at any depth."""
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in strings(item)]
    return [value] if isinstance(value, str) else []


def staff_strings(tree: dict) -> set[str]:
    """The texts that the fields for the staff only hold in a staff tree; of a
    drink on the staff list only its line (its name and category are shared)."""
    found = set()
    for kind, value in T.nodes(tree):
        for field, item in value.items():
            if field_name(kind, field) in STAFF_ONLY and not T.CHILDREN.get((kind, field)):
                found.update(strings(item))
            elif kind == "widget:drinks" and field == "list":
                found.update(drink["line"] for drink in item)
    return {text for text in found if len(text) > 2}


class DataLayerPageTests(unittest.TestCase):
    """The pages of the trees that the data layer builds from the fixture data.

    Every node is `Strict`: a field that a fragment reads and the data layer
    does not build fails the rendering, even inside an `if:`.
    """

    pages: list[tuple[str, dict, str, set[str]]]
    staff: dict[str, dict]

    @classmethod
    def setUpClass(cls):
        template = core.load_template(TEMPLATE)
        cls.pages, cls.staff = [], {}
        for name, build in fixtures.SETS.items():
            menu, guests = build()
            report = core.Report()
            _schema.check_data(menu, guests, report)
            trees = _page.build_trees(menu, guests, report)
            assert not report.errors, report.errors
            assert trees.staff is not None, name
            cls.staff[name] = trees.staff.tree
            for page in trees.guests + [trees.staff]:
                label = f"{name}: " + ("staff" if page.tree["isStaff"] else f"guest #{page.number}")
                reads: set[str] = set()
                document = render_strict(page.tree, template, reads)
                cls.pages.append((label, page.tree, document, reads))

    def test_every_page_renders_and_passes_the_checks_of_the_build(self):
        self.assertEqual({label.split(":")[0] for label, *_rest in self.pages},
                         set(fixtures.SETS))
        self.assertGreater(len(self.pages), len(fixtures.SETS) * 2)
        for label, _tree, document, _reads in self.pages:
            with self.subTest(page=label):
                core.check_rendered(document)
                self.assertEqual(html_problems(document), [])
                self.assertNotRegex(document, r"<[a-zA-Z][^>]*\sstyle\s*=")
                self.assertNotRegex(document, r"(?i)<style[\s>]")

    def test_the_nodes_have_exactly_the_fields_of_the_contract(self):
        seen = set()
        for label, tree, _document, _reads in self.pages:
            for kind, value in T.nodes(tree):
                seen.add(kind)
                with self.subTest(page=label, node=kind):
                    self.assertEqual(set(value), set(T.NODES[kind]))
        # the data sets reach every kind of node, the scheme of the table too
        self.assertEqual(seen, set(T.NODES))

    def test_every_field_of_the_contract_is_read_or_listed(self):
        reads = set().union(*(reads for *_rest, reads in self.pages))
        self.assertEqual(reads & set(UNREAD), set())
        self.assertEqual(CONTRACT - reads, set(UNREAD))

    def test_each_page_reads_the_fields_of_its_audience_only(self):
        for label, tree, _document, reads in self.pages:
            other = GUEST_ONLY if tree["isStaff"] else STAFF_ONLY
            with self.subTest(page=label):
                self.assertEqual(reads & other, set())

    def test_a_guest_page_shows_nothing_of_the_staff_page(self):
        for label, tree, document, _reads in self.pages:
            if tree["isStaff"]:
                continue
            text = visible_text(document)
            classes = {value for found in re.findall(r'class="([^"]*)"', document)
                       for value in found.split()}
            own = strings(tree)
            # a text of the staff tree that the guest's own tree also holds
            # (the guest's name, a word of an ingredient) is no leak
            hidden = {item for item in staff_strings(self.staff[label.split(":")[0]])
                      if not any(item in mine for mine in own)}
            with self.subTest(page=label):
                self.assertTrue(hidden)
                self.assertEqual(classes & set(STAFF_CLASSES), set())
                for word in STAFF_WORDS:
                    self.assertNotIn(word, text)
                leaks = [item for item in hidden
                         if re.search(r"(?<!\w)%s(?!\w)" % re.escape(item), text)]
                self.assertEqual(leaks, [])

    # --- the plan of the table on the pages of the data sets ---

    def plan_pages(self, name: str) -> list[tuple[str, dict, dict, str]]:
        """(label, tree, plan, drawing) of every page of a data set with a plan."""
        found = []
        for label, tree, document, _reads in self.pages:
            if label.startswith(f"{name}: "):
                plan = widgets_of(tree, "seating")[0]["scheme"]
                if plan is not None:
                    found.append((label, tree, plan, element(document, "scheme")))
        return found

    def guest_plan(self, name: str, seats: list[tuple[int, str]]) -> tuple[dict, str]:
        """The plan and the drawing of the guest whose own seats are `seats`."""
        found = [(plan, drawing) for label, tree, plan, drawing in self.plan_pages(name)
                 if not tree["isStaff"]
                 and [(seat["number"], seat["mark"])
                      for seat in widgets_of(tree, "seating")[0]["mySeats"]] == seats]
        self.assertEqual(len(found), 1, seats)
        return found[0]

    @staticmethod
    def nearest_seat(plan: dict, x: str, y: str) -> str:
        """The number of the seat whose centre is the nearest to the point."""
        return min(plan["seats"], key=lambda seat: (float(seat["cx"]) - float(x)) ** 2
                   + (float(seat["cy"]) - float(y)) ** 2)["number"]

    def test_the_tables_of_the_data_sets_are_drawn(self):
        for name in ("mockup16", "reserved19"):
            pages = self.plan_pages(name)
            with self.subTest(data=name):
                self.assertEqual(len(pages), len([label for label, *_rest in self.pages
                                                  if label.startswith(f"{name}: ")]))
                for label, tree, plan, drawing in pages:
                    if tree["isStaff"]:
                        # the couple label is the text of the tree, escaped
                        self.assertIn(f'<text class="scheme__couple" x="{plan["couple"]["x"]}" '
                                      f'y="{plan["couple"]["y"]}">'
                                      f'{core.text_to_html(plan["couple"]["text"])}</text>', drawing)
                    self.assertEqual(drawing.count('<g class="seat '), len(plan["seats"]))
                    self.assertEqual("aria-hidden" in drawing, tree["isStaff"], label)
        # no table: no drawing on any page of the data set
        for label, _tree, document, _reads in self.pages:
            if label.startswith("plain: "):
                with self.subTest(page=label):
                    self.assertNotIn("<svg", document)

    def own_colours(self, plan: dict, drawing: str) -> dict[str, str]:
        """The number of each own seat of the drawing -> its colour modifier."""
        found = re.findall(r'<g class="seat seat--you seat--none seat--colour-(\d)">'
                           r'<circle class="seat__ring" cx="([\d.-]+)" cy="([\d.-]+)"', drawing)
        return {self.nearest_seat(plan, x, y): colour for colour, x, y in found}

    def test_a_guest_with_a_companion_at_the_other_end_of_the_table(self):
        # the guest at seat 19 in the first colour, the +1 at seat 1 in the second
        plan, drawing = self.guest_plan("reserved19", [(1, "plusOne"), (19, "you")])
        self.assertEqual(self.own_colours(plan, drawing), {"19": "1", "1": "2"})
        self.assertNotIn("seat-label", drawing)
        self.assertNotIn("seat__number", drawing)
        self.assertIn('aria-label="Table plan: L-shaped table, 19 seats. Your seats: '
                      'Greta — blue, Hugo — dark red"', drawing)

    def test_a_record_for_two_has_two_own_seats_in_two_colours_and_no_label(self):
        plan, drawing = self.guest_plan("reserved19", [(2, "you"), (3, "none")])
        self.assertEqual(self.own_colours(plan, drawing), {"2": "1", "3": "2"})
        self.assertEqual(drawing.count('class="seat__ring"'), 2)
        self.assertNotIn("seat-label", drawing)
        self.assertIn("Your seats: Peggy — blue, Victor — dark red", drawing)

    def test_a_guest_of_one_seat_has_the_label_you(self):
        plan, drawing = self.guest_plan("reserved19", [(4, "you")])
        self.assertEqual(self.own_colours(plan, drawing), {"4": "1"})
        [(x, y, text)] = re.findall(r'<text class="seat-label[^"]*" x="([\d.-]+)" '
                                    r'y="([\d.-]+)">([^<]*)</text>', drawing)
        self.assertEqual((text, self.nearest_seat(plan, x, y)), ("You", "4"))
        self.assertIn("Your seat: Boris — blue", drawing)

    def test_the_couple_is_on_the_staff_plan_alone(self):
        for name in ("mockup16", "reserved19"):
            menu, _guests = fixtures.SETS[name]()
            for label, tree, plan, drawing in self.plan_pages(name):
                kinds = [seat["kind"] for seat in plan["seats"]]
                with self.subTest(page=label):
                    if tree["isStaff"]:
                        self.assertEqual(kinds.count("couple"), len(menu["couple"]["members"]))
                        self.assertIsNotNone(plan["couple"])
                        self.assertIn("seat seat--couple ", drawing)
                        self.assertIn("scheme__couple", drawing)
                    else:
                        self.assertNotIn("couple", kinds)
                        self.assertIsNone(plan["couple"])
                        for part in ("seat--couple", "scheme__couple", menu["couple"]["label"].upper()):
                            self.assertNotIn(part, drawing)

    def test_a_reserved_seat_is_a_plain_seat(self):
        menu, _guests = fixtures.reserved19()
        for label, tree, plan, drawing in self.plan_pages("reserved19"):
            for number in menu["reservedSeats"]:
                seat = plan["seats"][number - 1]
                # the number is on the staff plan alone
                number_text = f'<text class="seat__number" x="{seat["cx"]}" y="{seat["cy"]}">{number}</text>'
                with self.subTest(page=label, seat=number):
                    self.assertIn(f'<g class="seat seat--regular seat--none"><circle class="seat__circle" '
                                  f'cx="{seat["cx"]}" cy="{seat["cy"]}" r="14.25"/>'
                                  f'{number_text if tree["isStaff"] else ""}</g>', drawing)

    def test_the_staff_plan_has_the_badges_in_the_order_of_the_legend(self):
        for name in ("mockup16", "reserved19"):
            [(label, tree, plan, drawing)] = [page for page in self.plan_pages(name)
                                             if page[1]["isStaff"]]
            widget = widgets_of(tree, "seating")[0]
            order = [item["letter"] for item in widget["legend"]]
            badges = re.findall(r'<text class="seat-badge__letter" x="([\d.-]+)" '
                                r'y="([\d.-]+)">(\w)</text>', drawing)
            by_seat: dict[str, list[str]] = {}
            for x, y, letter in badges:
                by_seat.setdefault(self.nearest_seat(plan, x, y), []).append(letter)
            with self.subTest(data=name):
                self.assertEqual([letter for *_xy, letter in badges],
                                 [badge["letter"] for badge in plan["badges"]])
                for letters in by_seat.values():
                    self.assertEqual(letters, sorted(letters, key=order.index))
                # a badge per dietary need of the seat, a flagged seat per seat with needs
                needs = {str(row["number"]): len(row["tags"]) for row in widget["rows"]
                         if row["tags"]}
                self.assertEqual({seat: len(letters) for seat, letters in by_seat.items()}, needs)
                flagged = re.findall(r'<g class="seat seat--\w+ seat--flagged">.*?>(\d+)</text>',
                                     drawing)
                self.assertEqual(sorted(flagged, key=int), sorted(needs, key=int))
                classes = set(re.findall(r'class="([^"]*)"', drawing))
                self.assertEqual({value for found in classes for value in found.split()}
                                 & set(GUEST_CLASSES), set())

    def test_ids_headings_and_reveal_marks(self):
        for label, tree, document, _reads in self.pages:
            outline = Outline(document)
            custom = [section for section in tree["sections"] if section["type"] == "custom"]
            with self.subTest(page=label):
                self.assertEqual(len(outline.ids), len(set(outline.ids)))
                self.assertEqual([target for _name, target in outline.references
                                  if target not in outline.ids], [])
                self.assertEqual(outline.headings.count(1), 1)
                for previous, level in zip(outline.headings, outline.headings[1:]):
                    self.assertLessEqual(level, previous + 1)
                expected = 0 if tree["isStaff"] else len(custom)
                self.assertEqual(len(outline.reveals), expected)
                for _tag, attributes in outline.hidden:
                    self.assertIn("data-tabs-tablist", attributes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
