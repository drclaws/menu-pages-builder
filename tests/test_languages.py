"""Tests of the language of the pages: the plural rules, the words of a menu
over the English defaults, and a menu in Serbian (Latin script) from its data
to its pages.

The repository holds no Cyrillic: a plural rule depends on the language tag,
not on the script, so the rules are tested with ASCII forms, and a Cyrillic
letter is written as an escape only where the letter itself is the subject.
"""

import re
import unittest
from html.parser import HTMLParser

from tests import fixtures, support

from menu_tools import _core, _page, _schema, _words  # noqa: E402  (support prepares sys.path)

#: The numbers at the edges of the rules.
NUMBERS = (0, 1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111, 112)

#: The category of each of NUMBERS, by language tag.
_ONE_OTHER = "other one other other other other other other other other other other other other"
_EAST_SLAVIC = "many one few few many many many many one few many one many many"
_SOUTH_SLAVIC = "other one few few other other other other one few other one other other"
_ZERO_ONE = "one one other other other other other other other other other other other other"
CATEGORIES = {
    "en": _ONE_OTHER,
    "en-GB": _ONE_OTHER,
    "de": _ONE_OTHER,
    "ru": _EAST_SLAVIC,
    "uk": _EAST_SLAVIC,
    "be": _EAST_SLAVIC,
    "sr": _SOUTH_SLAVIC,
    "sr-Latn": _SOUTH_SLAVIC,
    "hr": _SOUTH_SLAVIC,
    "bs": _SOUTH_SLAVIC,
    "pl": "many one few few many many many many many few many many many many",
    "cs": "other one few few other other other other other other other other other other",
    "sk": "other one few few other other other other other other other other other other",
    "sl": "other one two few other other other other other other other one other other",
    "fr": _ZERO_ONE,
    "pt-BR": _ZERO_ONE,
    "ja": " ".join(["other"] * len(NUMBERS)),
    "zh-Hant": " ".join(["other"] * len(NUMBERS)),
    # a language without a built-in rule: one and other
    "tlh": _ONE_OTHER,
}

#: A form per category, in ASCII: the text names the category.
ASCII_FORMS = {category: f"{{n}} {category}" for category in _words.CATEGORIES}


def check(menu: dict, guests: list) -> tuple[list[str], list[str]]:
    report = _core.Report()
    _schema.check_data(menu, guests, report)
    return report.errors, report.warnings


def english_phrases() -> set[str]:
    """Every English default as the pages would show it: the texts, the
    parts of the patterns and of the plural forms around their placeholders,
    the colour names."""
    found = set()
    for value in _words.ENGLISH.values():
        texts = value.values() if isinstance(value, dict) else value if isinstance(value, tuple) else (value,)
        for text in texts:
            for part in re.split(r"\{\w+\}", text):
                part = part.strip(" ,")
                if part and (re.search(r"[^\W\d_]", part) or part == "&"):
                    found.add(part)
    return found


class _Texts(HTMLParser):
    """What a reader gets from a page: its text and the labels of its elements."""

    def __init__(self, page: str):
        super().__init__(convert_charrefs=True)
        self.texts: list[str] = []
        self.feed(page)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.texts += [value for name, value in attrs if name in ("aria-label", "title", "alt") and value]

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        if data.strip():
            self.texts.append(" ".join(data.split()))


def page_text(page: str) -> str:
    return "\n".join(_Texts(page).texts)


def shows(phrase: str, text: str) -> bool:
    """The phrase as words of the text; a phrase that starts with a mark
    ("’s guest", "&") may follow a word."""
    return support.occurs(phrase, text) or (not phrase[0].isalnum() and phrase in text)


# --------------------------------------------------------------------------
# Plural rules and the words of a menu
# --------------------------------------------------------------------------


class PluralRuleTest(unittest.TestCase):
    def test_the_categories_of_the_numbers_at_the_edges_of_the_rules(self):
        for tag, expected in CATEGORIES.items():
            words = _words.Words(tag, {"guestCount": ASCII_FORMS})
            with self.subTest(lang=tag):
                self.assertEqual([_words.guests_text(words, n) for n in NUMBERS],
                                 [f"{n} {category}" for n, category in zip(NUMBERS, expected.split())])

    def test_a_rule_picks_exactly_the_forms_it_names(self):
        for tag in CATEGORIES:
            rule = _words.plural_rule(tag) or _words.ONE_OTHER
            with self.subTest(lang=tag):
                self.assertEqual({rule.select(n) for n in range(1000)}, set(rule.forms))
                self.assertEqual(list(rule.forms), [item for item in _words.CATEGORIES if item in rule.forms])

    def test_the_rule_comes_from_the_language_subtag(self):
        self.assertIs(_words.plural_rule("SR-latn"), _words.plural_rule("sr"))
        self.assertIs(_words.plural_rule("en-GB"), _words.ONE_OTHER)
        self.assertEqual(_words.language("sr-Latn-RS"), "sr")
        self.assertIsNone(_words.plural_rule("tlh"))
        self.assertIs(_words.Words("tlh").rule, _words.ONE_OTHER)


class WordsTest(unittest.TestCase):
    def test_the_english_table(self):
        self.assertEqual(len(_words.ENGLISH), 28)
        for keys in (_words.PATTERNS, _words.PLURALS, _words.MARKUP_KEYS, (_words.COLOUR_NAMES,)):
            self.assertLessEqual(set(keys), set(_words.ENGLISH))
        # each English pattern holds exactly its placeholders, each form the number
        for key, value in _words.ENGLISH.items():
            with self.subTest(word=key):
                if key in _words.PLURALS:
                    self.assertEqual(set(value), {"one", "other"})
                    for form in value.values():
                        self.assertEqual(_words.placeholders(form), ["n"])
                elif key == _words.COLOUR_NAMES:
                    self.assertEqual(len(value), 3)
                else:
                    self.assertEqual(_words.placeholders(value), list(_words.PATTERNS.get(key, ())))

    def test_a_pattern_is_filled_in_one_pass(self):
        self.assertEqual(_words.fill("{a} and {b}", {"a": "{b}", "b": "x"}), "{b} and x")
        self.assertEqual(_words.fill("{a} {c}", {"a": "x"}), "x {c}")

    def test_a_menu_in_english_may_give_any_word(self):
        menu, guests = fixtures.reserved19()
        menu.update(lang="en-GB", strings={"and": "and", "seatsInline": "places",
                                           "guestCount": {"one": "{n} diner", "other": "{n} diners"}})
        self.assertEqual(check(menu, guests), ([], []))
        trees = _page.build_trees(menu, guests, _core.Report())
        staff = trees.staff.tree
        self.assertEqual((staff["lang"], staff["counters"]["guestsText"]), ("en-GB", "18 diners"))
        self.assertEqual(staff["strings"], _words.ENGLISH_WORDS.markup())
        (sets,) = [widget for section in staff["sections"] for widget in section["widgets"] if widget["type"] == "sets"]
        self.assertEqual(sets["items"][0]["swapLines"][1],
                         "By places 10 and 14 (no lactose) — serve the first course without sour cream.")
        for page in trees.guests:
            self.assertEqual(page.tree["lang"], "en-GB")


class LettersTest(unittest.TestCase):
    def test_a_badge_letter_is_any_one_capital_letter(self):
        # the last one is the Cyrillic capital Zhe
        for letter in ("A", "Š", "Ž", "Ø", "\u0416"):
            menu, guests = fixtures.serbian()
            menu["requirements"]["vegan"]["letter"] = letter
            with self.subTest(letter=letter):
                self.assertEqual(check(menu, guests), ([], []))
        # the Cyrillic small zhe is no capital
        for letter in ("ž", "\u0436", "ŽA", "1", "·"):
            menu, guests = fixtures.serbian()
            menu["requirements"]["vegan"]["letter"] = letter
            with self.subTest(letter=letter):
                self.assertEqual(check(menu, guests)[0],
                                 ["menu.json: field 'requirements.vegan.letter' must be one capital letter"])


class OccursTest(unittest.TestCase):
    def test_a_whole_word_in_any_script(self):
        self.assertTrue(support.occurs("Ana", "Ana i Miloš"))
        self.assertTrue(support.occurs("Miloš", "Ana i Miloš"))
        self.assertFalse(support.occurs("Ana", "Anađelka"))
        self.assertFalse(support.occurs("ana", "Žana"))
        # Cyrillic: Ana is no word of Anastasia
        ana = "\u0410\u043d\u0430"
        anastasia = "\u0410\u043d\u0430\u0441\u0442\u0430\u0441\u0438\u044f"
        self.assertFalse(support.occurs(ana, anastasia))
        self.assertTrue(support.occurs(ana, f"{ana}, {anastasia}"))


# --------------------------------------------------------------------------
# The Serbian menu from its data to its pages
# --------------------------------------------------------------------------


class SerbianBuildTest(support.TempDirTestCase):
    def build(self, menu: dict, guests: list, name: str = "serbian") -> dict[str, str]:
        """The pages of the data, by token."""
        data = fixtures.write_data(self.tmp / "data" / name, menu, guests)
        out = self.tmp / name
        result = support.run_main("build", "--data", data, "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return {token: (out / token / "index.html").read_text(encoding="utf-8") for token in fixtures.tokens(guests)}

    def test_the_data_is_clean(self):
        menu, guests = fixtures.serbian()
        data = fixtures.write_data(self.tmp / "data", menu, guests)
        result = support.run_main("validate", "--data", data)
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_every_page_is_in_serbian(self):
        phrases = english_phrases()
        self.assertLessEqual({"Dinner menu", "&", "seats", "You", "No.", "’s guest", "dark red", "By", "guests"},
                             phrases)
        # the English pages of the same menu show them (the data set has no
        # navigation bar, no singular count of notes and no third seat)
        menu, guests = fixtures.reserved19()
        shown = {phrase for page in self.build(menu, guests, "english").values()
                 for phrase in phrases if shows(phrase, page_text(page))}
        self.assertEqual(phrases - shown, {"Sections", "dietary note", "green"})
        menu, guests = fixtures.serbian()
        for token, page in self.build(menu, guests).items():
            text = page_text(page)
            with self.subTest(page=token):
                self.assertRegex(page, r'^<!doctype html>\n<html lang="sr-Latn" class="menu menu--(guest|staff)">')
                self.assertIn("<title>Jelovnik večere · Ivan i Vesna</title>", page)
                self.assertEqual([phrase for phrase in sorted(phrases) if shows(phrase, text)], [])

    def test_the_words_of_a_guest_page(self):
        menu, guests = fixtures.serbian()
        pages = self.build(menu, guests)
        bojan = page_text(pages["roda-7m2p"])
        self.assertIn("Raspored stola: Sto u obliku slova L, 19 mesta. Vaše mesto: Bojan — plava", bojan)
        self.assertIn("Vaše mesto", bojan.splitlines())
        self.assertRegex(pages["roda-7m2p"], r'<text class="seat-label seat-label--\w+" x="[\d.]+" y="[\d.]+">Vi</text>')
        self.assertIn("Uz meni: belo vino", bojan)
        olivera = page_text(pages["caplja-4tx9"])
        self.assertIn("Vaša mesta: Olivera — plava, vaš gost — tamnocrvena", olivera)
        self.assertIn("vaš gost", olivera.splitlines())
        self.assertNotIn("Vi</text>", pages["caplja-4tx9"])

    def test_the_words_of_the_staff_page(self):
        menu, guests = fixtures.serbian()
        page = self.build(menu, guests)["Vm7kQz2RtX9pLb4WnC6sYd"]
        lines = page_text(page).splitlines()
        for line in ("Verzija za osoblje · ne za goste", "ažurirano 12. jun 2030", "18 gostiju",
                     "7 napomena o ishrani", "Raspored sedenja i ishrana", "Br.", "Gost · napomene o ishrani",
                     "· gost: Olivera, [ime]", "· gost: Jelena", "bez ograničenja",
                     "Mesta 10 i 14 — umesto toga doneti voćni tanjir",
                     "Ako bira mesto 4 (bez orašastih plodova) — poslužiti drugo jelo bez korice.",
                     "Za mesta 10 i 14 (bez laktoze) — poslužiti prvo jelo bez kisele pavlake.",
                     "uz predjela · 6 boca · dobro rashlađeno · mesto 11 — bezalkoholno penušavo",
                     "Kontakt tokom večeri: Selma (organizatorka) · +00 000 000 00 00"):
            with self.subTest(line=line):
                self.assertIn(line, lines)
        # the badge letters with a diacritic, on the plan and in the legend
        self.assertIn('<span class="legend__mark" aria-hidden="true">Ž</span>', page)
        self.assertIn('<span class="legend__mark" aria-hidden="true">Č</span>', page)
        self.assertEqual(len(re.findall(r'<text class="seat-badge__letter" x="[\d.]+" y="[\d.]+">Ž</text>', page)), 2)

    def test_the_counters_take_the_forms_of_the_language(self):
        # the couple and two guests: 4 seats ("few"), 2 dietary notes ("few")
        menu, guests = fixtures.serbian()
        guests = [record for record in guests if record.get("name") in ("Bojan", "Gordana") or record.get("staff")]
        trees = _page.build_trees(menu, guests, _core.Report())
        self.assertEqual((trees.staff.tree["counters"]["guestsText"], trees.staff.tree["counters"]["notesText"]),
                         ("4 gosta", "2 napomene o ishrani"))
        guests = [record for record in guests if record.get("name") != "Gordana"]
        trees = _page.build_trees(menu, guests, _core.Report())
        self.assertEqual(trees.staff.tree["counters"]["guestsText"], "3 gosta")

    def test_every_english_word_given_by_the_menu_gives_the_same_pages(self):
        # the defaults and the same words from the data are the same pages
        menu, guests = fixtures.reserved19()
        default = self.build(menu, guests, "default")
        menu["strings"] = {key: list(value) if isinstance(value, tuple) else value
                           for key, value in _words.ENGLISH.items()}
        self.assertEqual(self.build(menu, guests, "given"), default)


if __name__ == "__main__":
    unittest.main()
