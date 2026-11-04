"""Static checks of the style sheet: sections, raw values, sources, sets, print."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "assets" / "app.css"

#: The numbered sections, in their order.
SECTIONS = (
    ("1", "Tokens"),
    ("1a", "Menu tokens"),
    ("2", "Fonts"),
    ("3", "Base"),
    ("4", "Layout primitives"),
    ("5", "Components"),
    ("5a", "Page"),
    ("6", "Scheme"),
    ("7", "Motion & reveal"),
    ("8", "Print"),
)

#: The sections where raw values (colours, lengths, durations) belong.
TOKEN_SECTIONS = ("1", "1a")

SECTION_RE = re.compile(r"^/\* =+\n   (\d+a?)\. (.+)$", re.MULTILINE)
RAW_VALUE_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|color-mix)\("
                          r"|(?<![\w.#-])\d*\.?\d+(?:px|rem|em|ms|s|vw|vh|svh|dvh)\b")
CONDITION_RE = re.compile(r"@media|@container|@supports")
PANELS = "html.js .sets__tabs:not([hidden]) ~ .sets__panels"

#: A math function whose arguments are scanned for bare factors.
MATH_RE = re.compile(r"\b(?:calc|min|max|clamp)\(")
#: A unitless number next to `*` or `/`: a size made from a token by a factor.
FACTOR_RE = re.compile(r"[*/]\s*(-?\d*\.?\d+)(?![\w.%(])|(?<![\w.#-])(-?\d*\.?\d+)\s*[*/]")
#: The factors allowed outside the token sections: a sign (`* -1`) and the
#: switch of the tab row (`* 999` turns a difference into all or nothing).
ALLOWED_FACTORS = frozenset({"-1", "999"})


def math_arguments(css):
    """The arguments of every outermost calc(), min(), max(), clamp() in the CSS."""
    found, position = [], 0
    while True:
        match = MATH_RE.search(css, position)
        if not match:
            return found
        depth, end = 0, match.end() - 1
        for end in range(match.end() - 1, len(css)):
            depth += {"(": 1, ")": -1}.get(css[end], 0)
            if depth == 0:
                break
        found.append(css[match.end():end])
        position = end + 1


def bare_factors(css):
    """Every unitless factor of a math function, but the allowed ones."""
    return [factor for arguments in math_arguments(css)
            for pair in FACTOR_RE.findall(arguments) for factor in pair
            if factor and factor not in ALLOWED_FACTORS]


def strip_comments(css):
    """The CSS without comments; line breaks are kept, so line numbers stay."""
    return re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), css, flags=re.S)


def rules(css):
    """{selector: body} of the innermost rules, whitespace collapsed (the first one wins)."""
    found = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        found.setdefault(" ".join(selector.split()), " ".join(body.split()))
    return found


def section_texts(css):
    """{"1": (first line, text), ...}: each numbered section up to the next one."""
    marks = list(SECTION_RE.finditer(css))
    texts = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(css)
        texts[mark.group(1)] = (css.count("\n", 0, mark.start()), css[mark.start():end])
    return texts


def media_blocks(css, condition):
    """The bodies of every `@media <condition> { ... }` block (one level of nesting)."""
    pattern = r"@media %s\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}" % re.escape(condition)
    return re.findall(pattern, css)


class StyleSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = APP_CSS.read_text(encoding="utf-8")
        cls.code = strip_comments(cls.raw)
        cls.marks = [(mark.group(1), mark.group(2).strip()) for mark in SECTION_RE.finditer(cls.raw)]
        cls.sections = section_texts(cls.raw)

    def section_code(self, number):
        return strip_comments(self.sections[number][1])

    def test_sections_are_in_place_and_in_order(self):
        self.assertEqual(self.marks, list(SECTIONS))

    def test_the_header_lists_every_section(self):
        header = self.raw[:self.raw.index("*/") + 2]
        positions = []
        for number, name in SECTIONS:
            with self.subTest(section=number):
                match = re.search(r"\n\s+%s\.\s+%s\s+- " % (re.escape(number), re.escape(name)), header)
                self.assertIsNotNone(match)
                positions.append(match.start())
        self.assertEqual(positions, sorted(positions))

    def test_no_raw_values_outside_the_token_sections(self):
        bad = []
        for number, (first_line, text) in self.sections.items():
            if number in TOKEN_SECTIONS:
                continue
            for offset, line in enumerate(strip_comments(text).split("\n")):
                if not CONDITION_RE.search(line) and RAW_VALUE_RE.search(line):
                    bad.append((first_line + offset + 1, line.strip()))
        self.assertEqual(bad, [])
        # what comes before the first section is the header comment only
        first = self.raw.index(self.sections["1"][1])
        self.assertEqual(strip_comments(self.raw[:first]).strip(), "")

    def test_no_sizes_made_by_a_factor_outside_the_token_sections(self):
        # `calc(var(--space-3xs) * 0.75)` is a raw value too: a size off the
        # scale of the tokens; it belongs in a named token of section 1a
        for number, (_first_line, text) in self.sections.items():
            if number not in TOKEN_SECTIONS:
                with self.subTest(section=number):
                    self.assertEqual(bare_factors(strip_comments(text)), [])

    def test_the_factor_check_tells_a_factor_from_a_token(self):
        for css in ("a { b: calc(var(--x) * 0.75); }", "a { b: calc(var(--x) / 2); }",
                    "a { b: calc(0.5 * var(--x)); }", "a { b: max(var(--x), calc(var(--y) * 2)); }",
                    "a { b: min(100%, calc(var(--x) * 1.5)); }"):
            with self.subTest(css=css):
                self.assertEqual(len(bare_factors(css)), 1)
        for css in ("a { b: calc(var(--x) * -1); }", "a { b: calc((var(--x) - 100%) * 999); }",
                    "a { b: calc(var(--x) * var(--y) / var(--z)); }",
                    "a { b: calc(var(--x, 1) - 1); }", "a { grid-column: 1 / -1; }",
                    "a { b: calc(var(--x) + 2px); }"):
            with self.subTest(css=css):
                self.assertEqual(bare_factors(css), [])

    def test_condition_numbers_match_their_tokens(self):
        # var() does not work in conditions: each number is repeated from a
        # token, and the comment right above names the token and its value
        conditions = list(re.finditer(r"@(?:media|container)[^{]*?\((?:min|max)-width:\s*([\d.]+\w+)\)",
                                      self.code))
        self.assertTrue(conditions)
        for condition in conditions:
            with self.subTest(condition=condition.group(0)):
                before = self.raw[:self.raw.index(condition.group(0))]
                comment = before[before.rindex("/*"):]
                named = re.search(r"(--[\w-]+) = ([\d.]+\w+)", comment)
                self.assertIsNotNone(named, comment)
                self.assertEqual(named.group(2), condition.group(1))
                token = re.search(r"\n\s*%s:\s*([^;]+);" % re.escape(named.group(1)), self.code)
                self.assertEqual(token.group(1).strip(), condition.group(1))

    def test_nothing_is_loaded_from_elsewhere(self):
        for pattern in (r"@import\b", r"\burl\(", r"@font-face\b", r"\bimage-set\(",
                        r"(?i)https?:", r"//"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.code, pattern)

    def test_hover_only_inside_hover_media_query(self):
        outside = re.sub(r"@media \(hover: hover\)\s*\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", self.code)
        self.assertNotIn(":hover", outside)
        self.assertIn(".sets__tab:hover", self.code)

    def test_hidden_beats_the_display_of_components(self):
        self.assertEqual(rules(self.section_code("3"))["[hidden]"], "display: none !important;")

    def test_no_styles_of_link_buttons(self):
        # the pages have no link button, so no rule styles one; its tokens
        # stay in section 1, a copy of the tokens of the invitations
        self.assertNotRegex(self.code, r"\.btn\b")
        self.assertIn("--btn-padding-block:", self.section_code("1"))
        header = self.raw[:self.raw.index("*/") + 2]
        self.assertNotIn("button", header)


class SetSwitcherStylesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = APP_CSS.read_text(encoding="utf-8")
        cls.code = strip_comments(raw)
        sections = section_texts(raw)
        cls.components = strip_comments(sections["5"][1])
        cls.print = strip_comments(sections["8"][1])

    def test_without_the_script_the_cards_follow_each_other(self):
        found = rules(self.components)
        self.assertEqual(found[".sets__panel + .sets__panel"], "margin-block-start: var(--space-lg);")
        # nothing hides a card or the room of a card unless the script runs
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", self.code):
            if re.search(r"visibility:\s*hidden|grid-area", body):
                with self.subTest(selector=selector.strip()):
                    self.assertTrue(" ".join(selector.split()).startswith(PANELS + " >"))

    def test_with_the_script_the_cards_share_one_cell(self):
        found = rules(self.components)
        self.assertEqual(found[PANELS], "display: grid; grid-template-columns: minmax(0, 1fr); "
                                        "margin-block-start: var(--space-md);")
        self.assertEqual(found[PANELS + " > .sets__panel"], "grid-area: 1 / 1; margin-block-start: 0;")
        # the hidden card keeps its room but is not shown, read or focused;
        # it has to beat [hidden] { display: none !important }
        self.assertEqual(found[PANELS + " > .sets__panel[hidden]"],
                         "display: block !important; visibility: hidden;")

    def test_print_shows_every_card_one_after_another(self):
        blocks = media_blocks(self.print, "print")
        self.assertEqual(len(blocks), 1)
        # section 8 is print rules only
        self.assertEqual(re.sub(r"@media print\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", "", self.print).strip(), "")
        found = rules(blocks[0])
        self.assertEqual(found[".sets__tabs"], "display: none;")
        self.assertEqual(found[PANELS], "display: block; margin-block-start: 0;")
        self.assertEqual(found[PANELS + " > .sets__panel[hidden]"], "visibility: visible;")
        self.assertEqual(found[PANELS + " > .sets__panel + .sets__panel"],
                         "margin-block-start: var(--space-lg);")

    def test_the_tab_width_is_a_menu_token(self):
        self.assertIn("var(--sets-tab-min)", self.components)
        self.assertNotIn("--events-tab-min", self.components)
        self.assertNotIn("--events-count", self.code)


class MenuStylesTest(unittest.TestCase):
    """The components of the menu (section 5), the page (5a) and its print (8)."""

    @classmethod
    def setUpClass(cls):
        raw = APP_CSS.read_text(encoding="utf-8")
        sections = section_texts(raw)
        cls.components = rules(strip_comments(sections["5"][1]))
        cls.page_code = strip_comments(sections["5a"][1])
        cls.page = rules(cls.page_code)
        cls.print = rules(media_blocks(strip_comments(sections["8"][1]), "print")[0])

    def test_the_components_are_in_section_5(self):
        for selector in (".note-line", ".pills", ".pill", ".pill--flag", ".pill--plain",
                         ".legend", ".legend__mark", ".seat-table", ".seat-number",
                         ".seat-number--couple", ".seating__meta", ".text-widget--card",
                         ".text-widget--signature", ".dishes", ".dish", ".drink",
                         ".schedule--ruled .schedule__item", ".staff-bar", ".staff-footer",
                         ".sets__head", ".sets__pairing, .sets__swaps", ".sets__note"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.components)

    def test_the_page_is_in_section_5a(self):
        for selector in (".cover", ".cover--staff", ".cover__counters", ".menu--staff body"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.page)
        # the page depends on the audience alone, never on the width
        self.assertNotRegex(self.page_code, r"@media|@container")

    def test_the_flags_use_the_menu_tokens(self):
        self.assertEqual(self.components[".pill--flag"],
                         "border-color: var(--color-flag-line); "
                         "background-color: var(--color-flag-bg); "
                         "color: var(--color-flag-text); "
                         "font-weight: var(--font-weight-heading);")
        mark = self.components[".legend__mark"]
        self.assertIn("background-color: var(--color-flag);", mark)
        self.assertIn("color: var(--color-on-flag);", mark)
        self.assertIn("border-radius: var(--radius-round);", mark)

    def test_an_empty_row_of_pills_takes_no_room(self):
        self.assertEqual(self.components[".pills:empty"], "display: none;")

    def test_the_courses_are_numbered_by_a_counter_of_the_list(self):
        self.assertIn("counter-reset: course;", self.components[".sets__courses"])
        self.assertIn("counter-increment: course;", self.components[".sets__courses > .dish"])
        self.assertIn("content: counter(course);", self.components[".sets__courses > .dish::before"])

    def test_the_audience_sets_the_alignment_and_the_type_size(self):
        self.assertEqual(self.page[".menu--guest .cover, .menu--guest .section"],
                         "text-align: center;")
        self.assertEqual(self.page[".menu--guest .card, .menu--guest .text-widget--card"],
                         "text-align: start;")
        # one step of the body text larger: 17px at a 16px root
        self.assertEqual(self.page[".menu--staff body"],
                         "font-size: calc(var(--text-base) * var(--text-base-desktop) "
                         "/ var(--text-base-mobile));")

    def test_print_keeps_the_background_colours_of_flags_and_labels(self):
        self.assertEqual(self.print[".legend__mark, .pill, .seat-number--couple, "
                                    ".time-label--strong, .staff-bar"],
                         "-webkit-print-color-adjust: exact; print-color-adjust: exact;")

    def test_print_of_the_staff_page_is_compact(self):
        self.assertEqual(self.print[".menu--staff .section"], "margin-block: var(--space-md);")
        # a part after another one: the step of the sections, not the larger one of the screen
        self.assertEqual(self.print[".menu--staff .section__body > * + .heading-widget"],
                         "margin-block-start: var(--space-md);")
        self.assertEqual(self.print[".seat-table td"], "padding-block: var(--space-3xs);")
        self.assertEqual(self.print[".seat-number"], "padding-block: 0;")
        self.assertEqual(self.print[".seat-table tr"], "break-inside: avoid;")
        self.assertEqual(self.print[".sets__panel"], "break-inside: avoid;")

    def test_print_keeps_the_head_of_a_section_with_what_follows(self):
        # both: with `break-after` alone a browser splits the eyebrow from the
        # title; the heading of a part is kept with its part the same way
        self.assertEqual(self.print[".section__head, .heading-widget"], "break-inside: avoid; break-after: avoid;")

    def test_the_heading_of_a_part_is_a_component(self):
        self.assertEqual(self.components[".heading-widget__title"], "font-size: var(--text-lg);")
        self.assertEqual(self.components[".heading-widget .heading-widget__eyebrow"],
                         "margin-block: var(--space-2xs) 0;")
        # a part after another one stands a larger step apart
        self.assertEqual(self.components[".section__body > * + .heading-widget"],
                         "margin-block-start: var(--space-xl);")

    def test_print_drops_the_shadows_of_the_cards(self):
        # a browser prints the blur of a rounded card as a grey rectangle
        self.assertEqual(self.print[".card, .text-widget--card"], "box-shadow: none;")

    def test_print_never_splits_a_dish_a_drink_or_the_staff_footer(self):
        self.assertEqual(
            self.print[".dish, .drink, .schedule__item, .drinks__group--inline, .staff-footer"],
            "break-inside: avoid;",
        )

    def test_print_of_the_staff_footer_is_compact(self):
        # as compact as the sections of the staff page
        self.assertEqual(self.print[".menu--staff .page-footer"], self.print[".menu--staff .section"])
        self.assertEqual(self.print[".menu--staff .page-footer"], "margin-block: var(--space-md);")


class SectionNavStylesTest(unittest.TestCase):
    """The line of the sections: it sticks on the screen, it is not printed,
    a jump to a section glides unless less motion is asked for, the body
    scrolls the page on a touch screen."""

    @classmethod
    def setUpClass(cls):
        raw = APP_CSS.read_text(encoding="utf-8")
        cls.code = strip_comments(raw)
        sections = section_texts(raw)
        cls.base = strip_comments(sections["3"][1])
        cls.components = strip_comments(sections["5"][1])
        cls.page = rules(strip_comments(sections["5a"][1]))
        cls.print = rules(media_blocks(strip_comments(sections["8"][1]), "print")[0])
        cls.tokens = rules(strip_comments(sections["1a"][1]))[":root"]
        # the code with every @media block taken out: what applies everywhere
        cls.outside = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", cls.code)

    def media(self, css, condition):
        blocks = media_blocks(css, condition)
        self.assertEqual(len(blocks), 1, condition)
        return rules(blocks[0])

    def test_the_line_sticks_on_the_screen_only(self):
        self.assertEqual(self.media(self.components, "screen")[".section-nav"],
                         "position: sticky; inset-block-start: 0; z-index: var(--z-sticky);")
        sticky = [selector for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", self.outside)
                  if re.search(r"position:\s*sticky", body)]
        self.assertEqual(sticky, [])
        line = rules(self.components)[".section-nav"]
        self.assertIn("block-size: var(--section-nav-block-size);", line)
        self.assertIn("position: relative;", line)

    def test_the_line_is_not_printed(self):
        self.assertEqual(self.print[".section-nav"], "display: none;")
        self.assertEqual(self.print[".section__head, .heading-widget"], "break-inside: avoid; break-after: avoid;")

    def test_a_jump_glides_unless_less_motion_is_asked_for(self):
        self.assertEqual(self.media(self.base, "(prefers-reduced-motion: no-preference)")["html.menu, html.menu body"],
                         "scroll-behavior: smooth;")
        self.assertNotRegex(self.outside, r"scroll-behavior:\s*smooth")
        self.assertEqual(len(re.findall(r"scroll-behavior:\s*smooth", self.code)), 1)
        reduce = self.media(self.base, "(prefers-reduced-motion: reduce)")
        self.assertIn("scroll-behavior: auto !important;", reduce["*, *::before, *::after"])

    def test_a_target_stops_under_the_line(self):
        padding = "scroll-padding-block-start: calc(var(--section-nav-block-size) + var(--section-nav-gap));"
        self.assertEqual(rules(self.base)["html.menu"], padding)
        touch = self.media(self.base, "screen and (pointer: coarse)")
        self.assertIn(padding, touch["html.menu body"])
        self.assertIn("var(--tap-min)", re.search(r"--section-nav-size:([^;]+);", self.tokens).group(1))
        self.assertEqual(re.search(r"--section-nav-block-size:([^;]+);", self.tokens).group(1).strip(),
                         "calc(var(--section-nav-size) + var(--safe-inset-top) + var(--line-width-hairline))")

    def test_the_body_scrolls_the_page_on_a_touch_screen_only(self):
        touch = self.media(self.base, "screen and (pointer: coarse)")
        self.assertEqual(touch["html.menu"], "block-size: 100%; overflow: hidden;")
        self.assertTrue(touch["html.menu body"].startswith("block-size: 100%; min-block-size: 0; overflow-y: auto;"))
        # nowhere else does the document stop scrolling
        self.assertNotRegex(self.outside, r"html\.menu[^{]*\{[^}]*overflow")
        # the canvas in the colour of the line, a body as tall as the screen: on the screen
        screen = self.media(self.base, "screen")
        self.assertEqual(screen["html.menu"], "background-color: var(--color-surface);")
        self.assertIn("min-block-size: var(--viewport-height-dynamic);", screen["html.menu body"])

    def test_the_end_of_the_page_is_on_its_background(self):
        # the margin of the last block stays inside the body, on the background
        # of the page, and the safe area at the foot of the screen adds to it
        screen = self.media(self.base, "screen")
        self.assertEqual(screen["html.menu body"],
                         "display: flow-root; min-block-size: var(--viewport-height-dynamic); "
                         "padding-block-end: var(--safe-inset-bottom);")
        self.assertNotIn("flow-root", self.outside)
        # that margin is the air between two sections, after a section or the staff footer
        components = rules(self.components)
        self.assertEqual(components[".section"], "margin-block: var(--space-section);")
        self.assertEqual(components[".page-footer"], "margin-block: var(--space-section);")
        # the body that scrolls on a touch screen keeps the padding
        touch = self.media(self.base, "screen and (pointer: coarse)")
        self.assertNotRegex(touch["html.menu body"], r"(?<![\w-])padding[\w-]*:")
        # print keeps the end of the document as it is
        for selector, body in self.print.items():
            if "body" in selector:
                with self.subTest(selector=selector):
                    self.assertNotRegex(body, r"(?<![\w-])(?:display|padding[\w-]*):")

    def test_the_fill_above_the_line_and_the_staff_bar_over_it(self):
        components = rules(self.components)
        fill = components[".section-nav::before"]
        for declaration in ('content: "";', "position: absolute;", "inset-block-end: 100%;",
                            "block-size: var(--viewport-height);", "background-color: inherit;",
                            "pointer-events: none;"):
            self.assertIn(declaration, fill)
        self.assertIn("z-index: calc(var(--z-sticky) + var(--z-raised));", components[".staff-bar"])

    def test_the_links_are_targets_for_a_finger_and_the_list_scrolls_by_itself(self):
        components = rules(self.components)
        link = components[".section-nav__link"]
        self.assertIn("min-inline-size: var(--tap-min);", link)
        self.assertIn("min-block-size: var(--tap-min);", link)
        self.assertIn("white-space: nowrap;", link)
        listing = components[".section-nav__list"]
        self.assertIn("overflow-x: auto;", listing)
        self.assertIn("display: flex;", listing)
        # the focus ring inside the link: the scrolling list would cut it outside
        self.assertEqual(components[".section-nav__link:focus-visible"],
                         "outline-offset: var(--focus-ring-offset-inset);")
        self.assertIn("box-shadow:", components['.section-nav__link[aria-current="true"]'])
        # the guest page centres the links while they fit, the staff page starts at the left
        self.assertEqual(self.page[".menu--guest .section-nav__item:first-child"], "margin-inline-start: auto;")
        self.assertEqual(self.page[".menu--guest .section-nav__item:last-child"], "margin-inline-end: auto;")
        self.assertNotRegex(" ".join(self.page), r"menu--staff \.section-nav")


def declarations(body: str) -> dict[str, str]:
    """{property: value} of a rule body as `rules()` gives it."""
    found = {}
    for declaration in body.split(";"):
        name, colon, value = declaration.partition(":")
        if colon:
            found[name.strip()] = " ".join(value.split())
    return found


class SchemeStylesTest(unittest.TestCase):
    """The table scheme (section 6) and its print (section 8)."""

    #: The colours of the seats of a guest, as the geometry numbers them.
    COLOURS = ("1", "2", "3")
    #: The parts of the drawing that have rules; seat--regular and seat--none
    #: are modifiers of the enumerations that need none. A colour modifier
    #: of a seat colours the name of that seat under the scheme too.
    PARTS = (".scheme", ".scheme__table", ".scheme__couple", ".seat__circle", ".seat__number",
             ".seat--couple .seat__circle", ".seat--flagged .seat__circle",
             *(f".seat--colour-{colour}, .seating__name--colour-{colour}" for colour in COLOURS),
             ".seat--you .seat__circle", ".seat__ring",
             ".seat-badge__circle", ".seat-badge__letter", ".seat-label", ".seat-label--start",
             ".seat-label--end", ".seat-label--middle")

    @classmethod
    def setUpClass(cls):
        raw = APP_CSS.read_text(encoding="utf-8")
        sections = section_texts(raw)
        cls.code = strip_comments(sections["6"][1])
        cls.scheme = {selector: declarations(body) for selector, body in rules(cls.code).items()}
        cls.print = {selector: declarations(body) for selector, body in
                     rules(media_blocks(strip_comments(sections["8"][1]), "print")[0]).items()}
        cls.tokens = rules(strip_comments(sections["1a"][1]))[":root"]

    def token(self, name: str) -> str:
        return re.search(r"%s:\s*([^;]+);" % re.escape(name), self.tokens).group(1).strip()

    def test_every_part_of_the_drawing_has_its_rule_and_nothing_else(self):
        self.assertEqual(sorted(self.scheme), sorted(self.PARTS))
        self.assertNotRegex(self.code, r"seat--regular|seat--none|@media|@container")

    def test_the_field_fills_the_card_padding_then_shrinks(self):
        # the width comes from the width attribute of the drawing (the size of
        # its field), the height from the ratio of its viewBox: no inline
        # size and no ratio here, the style sheet knows no size of a field
        field = self.scheme[".scheme"]
        self.assertEqual(field, {
            "justify-self": "center",
            "max-inline-size": "calc(100% + var(--card-padding) + var(--card-padding) - "
                               "var(--seating-bleed-gap) - var(--seating-bleed-gap))",
            "block-size": "auto",
            "margin-inline": "calc(var(--seating-bleed-gap) - var(--card-padding))",
            "overflow": "visible",
        })
        self.assertNotRegex(self.code, r"(?<![\w-])(inline-size|width|height)\s*:|aspect-ratio")

    def test_the_borders_of_the_seats_are_their_tokens(self):
        self.assertEqual(self.scheme[".seat__circle"]["stroke-width"], "var(--line-width-seat)")
        self.assertEqual(self.scheme[".seat--flagged .seat__circle"]["stroke-width"],
                         "var(--line-width-flag)")
        widths = {selector: values["stroke-width"] for selector, values in self.scheme.items()
                  if "stroke-width" in values}
        self.assertEqual(widths, {".scheme__table": "var(--line-width-hairline)",
                                  ".seat__circle": "var(--line-width-seat)",
                                  ".seat--flagged .seat__circle": "var(--line-width-flag)"})

    def test_colours_and_type_are_tokens(self):
        for selector, values in self.scheme.items():
            for name, value in values.items():
                with self.subTest(selector=selector, property=name):
                    if name in ("fill", "stroke"):
                        # a token, or the colour of the seat set by its modifier
                        self.assertRegex(value, r"\Avar\((--color-[\w-]+|--seat-colour)\)\Z")
                    if name == "font-size":
                        self.assertRegex(value, r"\Avar\(--scheme-font-[\w-]+\)\Z")
                    if name == "font-weight":
                        self.assertIn(value, ("var(--font-weight-heading)",
                                              "var(--scheme-font-weight-strong)"))
        self.assertEqual(self.token("--scheme-font-weight-strong"), "700")
        self.assertEqual(self.scheme[".seat__ring"]["fill-opacity"], "var(--seat-ring-opacity)")

    def test_the_seats_of_a_guest_and_their_names_take_the_colour_of_their_place(self):
        # a token holds each colour (tests/test_scheme.py ties the tokens to
        # the colours of the geometry and checks their values)
        for colour in self.COLOURS:
            with self.subTest(colour=colour):
                self.assertEqual(self.scheme[f".seat--colour-{colour}, .seating__name--colour-{colour}"],
                                 {"--seat-colour": f"var(--color-seat-{colour})"})
                self.assertIn(f"--color-seat-{colour}:", self.tokens)
        own = {"fill": "var(--seat-colour)", "stroke": "var(--seat-colour)"}
        self.assertEqual(self.scheme[".seat--you .seat__circle"], own)
        self.assertEqual(self.scheme[".seat__ring"]["fill"], "var(--seat-colour)")
        # "You" stands by the one seat of a record of one seat: the first colour
        self.assertEqual(self.scheme[".seat-label"]["fill"], "var(--color-seat-1)")
        # the guest page prints no numbers: no rule for a number of a guest's seat
        self.assertNotIn(".seat--you .seat__number", self.scheme)
        name = declarations(rules(strip_comments(section_texts(APP_CSS.read_text(encoding="utf-8"))["5"][1]))
                            [".seating__name"])
        self.assertEqual((name["background-color"], name["border-color"], name["white-space"]),
                         ("var(--seat-colour)", "var(--seat-colour)", "normal"))

    def test_the_scheme_has_no_text_transform(self):
        # the build writes the couple label in capitals: WebKit misplaces the
        # letters of an SVG text with text-transform
        self.assertNotIn("text-transform", self.code)

    def test_print_keeps_the_scheme_whole_and_in_its_colours(self):
        self.assertEqual(self.print[".scheme"], {"break-inside": "avoid",
                                                 "-webkit-print-color-adjust": "exact",
                                                 "print-color-adjust": "exact"})
        # the guest's card (the scheme and the names of the seats) stays whole
        guest_card = ".menu--guest .seating__card"
        self.assertEqual(self.print[guest_card], {"break-inside": "avoid"})
        self.assertNotIn(".seating__meta", self.print)
        # the staff card may break: taller than the rest of a sheet it would
        # move whole onto the next one
        for selector, values in self.print.items():
            if "seating" in selector and selector != guest_card:
                with self.subTest(selector=selector):
                    self.assertNotIn("break-inside", values)
        self.assertNotIn("break-inside", self.print[".menu--staff .seating__card"])

    def test_print_tells_a_flagged_seat_and_the_guest_seat_in_black_and_white(self):
        self.assertEqual(self.print[".seat--flagged .seat__circle"],
                         {"stroke-width": "var(--line-width-flag-print)"})
        self.assertEqual(self.print[".seat__ring"],
                         {"fill-opacity": "var(--seat-ring-opacity-print)"})
        self.assertGreater(float(self.token("--line-width-flag-print").removesuffix("px")),
                           float(self.token("--line-width-flag").removesuffix("px")))
        self.assertGreater(float(self.token("--seat-ring-opacity-print")),
                           float(self.token("--seat-ring-opacity")))

    def test_print_of_the_staff_page_sets_the_scheme_beside_the_table(self):
        card = ".menu--staff .seating__card"
        self.assertEqual(self.print[card]["grid-template-columns"], "auto minmax(0, 1fr)")
        self.assertEqual(self.print[f"{card} > *"], {"grid-column": "1 / -1"})
        self.assertEqual(self.print[f"{card} > .scheme"],
                         {"grid-column": "1", "max-inline-size": "none",
                          "margin-inline": "0 var(--space-md)"})
        self.assertEqual(self.print[f"{card} > .seat-table"], {"grid-column": "2"})
        self.assertEqual(self.print[".menu--staff .seating__divider"], {"display": "none"})
        self.assertEqual(self.print[".menu--staff .container"], {"max-width": "none"})


if __name__ == "__main__":
    unittest.main()
