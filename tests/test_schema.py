"""Tests of the menu data checks (`menu_tools._schema`), standard library only.

Every broken copy of the fictional data (`CASES`) changes one thing and
expects the exact messages; none of them may quote a token or a name.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, NamedTuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core, _page, _schema, _words  # noqa: E402  (imported after sys.path is prepared)
from tests import fixtures  # noqa: E402

M = "menu.json: "


def G(number: int) -> str:
    return f"guests.json: guest #{number}: "


def check(menu, guests) -> tuple[_schema.MenuIndex, list[str], list[str]]:
    """The index and the check messages for both documents."""
    report = _core.Report()
    index = _schema.check_data(menu, guests, report)
    return index, report.errors, report.warnings


def full_check(menu, guests) -> tuple[list[str], list[str]]:
    """The check messages and, when there is no error, those about what the
    page trees show."""
    report = _core.Report()
    index = _schema.check_data(menu, guests, report)
    if not report.errors:
        trees = _page.build_trees(menu, guests, report)
        _schema.check_usage(index, menu, trees.usage, report)
    return report.errors, report.warnings


def secrets_of(menu, guests) -> set[str]:
    """What no message may show: every token and every name of the data."""
    found = fixtures.tokens(guests) | fixtures.names(guests, menu)
    return {item for item in found if item.strip()}


class Case(NamedTuple):
    name: str
    base: str
    change: Callable
    errors: list
    warnings: list


#: Broken copies of the fixtures: one change, the exact messages.
CASES: list[Case] = []


def case(name: str, *, base: str = "reserved19", errors=(), warnings=()):
    def register(change: Callable) -> Callable:
        CASES.append(Case(name, base, change, list(errors), list(warnings)))
        return change
    return register


def record(guests: list, name: str) -> dict:
    """The record of the guest with this name."""
    return next(item for item in guests if item.get("name") == name)


def kitchen_section(**widget) -> dict:
    """A section for the staff only."""
    return {
        "id": "kitchen",
        "title": "Kitchen",
        "audience": "staff",
        "widgets": [{"type": "text", "text": "Serve the starters by 19:15.", **widget}],
    }


# --------------------------------------------------------------------------
# menu.json
# --------------------------------------------------------------------------


@case("misspelt_dish_field", errors=[M + "unknown field 'dishes.hummus.ingredient' (did you mean 'ingredients'?)"])
def _(menu, guests):
    dish = menu["dishes"]["hummus"]
    dish["ingredient"] = dish.pop("ingredients")


@case("unknown_top_level_field", errors=[M + "unknown field 'dish' (did you mean 'dishes'?)"])
def _(menu, guests):
    menu["dish"] = {}


@case(
    "unsupported_version",
    errors=[M + "field 'schemaVersion' is 2 - not supported: this builder reads version 1 only"],
)
def _(menu, guests):
    menu["schemaVersion"] = 2


@case(
    "swap_for_an_unknown_requirement",
    errors=[
        M + "field 'dishes.bruschetta.staff.swaps.glutn' refers to an unknown requirement 'glutn' "
        "(did you mean 'gluten'?); known: nuts, gluten, lactose, vegan, alcohol"
    ],
)
def _(menu, guests):
    menu["dishes"]["bruschetta"]["staff"]["swaps"]["glutn"] = "serve it without bread"


@case("letter_repeated", errors=[M + "field 'requirements.vegan.letter' repeats the letter of 'nuts'"])
def _(menu, guests):
    menu["requirements"]["vegan"]["letter"] = "N"


@case("letter_in_lower_case", errors=[M + "field 'requirements.alcohol.letter' must be one capital letter"])
def _(menu, guests):
    menu["requirements"]["alcohol"]["letter"] = "a"


@case("two_letters", errors=[M + "field 'requirements.alcohol.letter' must be one capital letter"])
def _(menu, guests):
    menu["requirements"]["alcohol"]["letter"] = "AL"


@case(
    "unknown_widget_type",
    errors=[
        M + "field 'sections[2].widgets[0].type' names an unknown widget type 'dish' (did you mean 'dishes'?); "
        "known: text, seating, dishes, sets, drinks, heading"
    ],
)
def _(menu, guests):
    menu["sections"][2]["widgets"][0]["type"] = "dish"


@case(
    "link_is_no_widget_type",
    errors=[
        M + "field 'sections[5].widgets[1].type' names an unknown widget type 'link' (did you mean 'drinks'?); "
        "known: text, seating, dishes, sets, drinks, heading"
    ],
)
def _(menu, guests):
    menu["sections"][5]["widgets"].append({"type": "link"})


@case("a_link_back_is_an_unknown_field", errors=[M + "unknown field 'backLink'"])
def _(menu, guests):
    menu["backLink"] = {"text": "Back", "href": "/{token}/"}


@case("two_seating_widgets", errors=[M + "field 'sections' has 2 seating widgets; there may be only one"])
def _(menu, guests):
    menu["sections"][3]["widgets"].append({"type": "seating"})


@case("section_without_a_title", errors=[M + "field 'sections[2].title' is required"])
def _(menu, guests):
    del menu["sections"][2]["title"]


@case("section_id_repeated", errors=[M + "field 'sections[3].id' repeats 'starters' (already used by sections[2])"])
def _(menu, guests):
    menu["sections"][3]["id"] = "starters"


@case("cover_not_first", errors=[M + "field 'sections[1].type' is 'cover': the cover must be the first section"])
def _(menu, guests):
    sections = menu["sections"]
    sections[0], sections[1] = sections[1], sections[0]


@case("widget_id_repeated", errors=[M + "field 'sections[3].widgets[1].id' repeats 'allergy-card' within the section"])
def _(menu, guests):
    menu["sections"][3]["widgets"][0]["id"] = "allergy-card"


@case(
    "guest_widget_in_a_staff_section",
    errors=[M + "field 'sections[6].widgets[0].audience' is 'guest' in a section for 'staff': nobody sees it"],
)
def _(menu, guests):
    menu["sections"].append(kitchen_section(audience="guest"))


@case(
    "hidden_staff_section",
    warnings=[M + "field 'sections[6].visible' hides a part for the staff only: no page ever shows it (a guest cannot switch it on)"],
)
def _(menu, guests):
    # its hidden widget is not reported again
    menu["sections"].append({**kitchen_section(visible=False), "visible": False})


@case(
    "hidden_staff_widget",
    warnings=[
        M + "field 'sections[3].widgets[2].visible' hides a part for the staff only: no page ever shows it "
        "(a guest cannot switch it on)"
    ],
)
def _(menu, guests):
    menu["sections"][3]["widgets"].append(
        {"type": "text", "audience": "staff", "visible": False, "text": "Serve the sets warm."}
    )


@case(
    "staff_widget_in_a_guest_section",
    errors=[M + "field 'sections[5].widgets[0].audience' is 'staff' in a section for 'guest': nobody sees it"],
)
def _(menu, guests):
    menu["sections"][5]["widgets"][0]["audience"] = "staff"


@case(
    "template_syntax_in_a_dish_name",
    errors=[M + "field 'dishes.hummus.name' must not contain '{{' or '}}' (menu texts have no template syntax)"],
)
def _(menu, guests):
    menu["dishes"]["hummus"]["name"] = "Hummus {{ name }}"


@case(
    "token_in_a_text",
    errors=[M + "field 'sections[3].widgets[1].text' must not contain '{token}': menu pages hold no token"],
)
def _(menu, guests):
    menu["sections"][3]["widgets"][1]["text"] = "Your page: {token}"


@case(
    "token_in_a_staff_text",
    errors=[M + "field 'staff.reminder' must not contain '{token}': menu pages hold no token"],
)
def _(menu, guests):
    menu["staff"]["reminder"] = "The staff page is /menu/{token}/"


@case(
    "drink_of_an_unknown_category",
    errors=[
        M + "field 'drinks.items.water.category' refers to an unknown category 'softs' (did you mean 'soft'?); "
        "known: sparkling, white, red, soft"
    ],
)
def _(menu, guests):
    menu["drinks"]["items"]["water"]["category"] = "softs"


@case("set_without_courses", errors=[M + "field 'sets.fish.courses' must list at least one dish"])
def _(menu, guests):
    menu["sets"]["fish"]["courses"] = []


@case("couple_member_without_a_name", errors=[M + "field 'couple.members[0].name' is required"])
def _(menu, guests):
    del menu["couple"]["members"][0]["name"]


@case("arm_outside_the_field", errors=[M + "table.arms[1]: lies outside the 318x310 field"])
def _(menu, guests):
    menu["table"]["arms"][1]["height"] = 300


@case(
    "seats_aligned_in_a_circle",
    errors=[M + "table.seats[0].align[0] (seat 1): the alignment goes round in a circle through seats 1, 8"],
)
def _(menu, guests):
    menu["table"]["seats"][0]["align"] = [8]
    menu["table"]["seats"][2]["align"] = [1, None, None, None, None]


@case("couple_on_an_unknown_arm", errors=[M + "couple.arm: not an id of table.arms"])
def _(menu, guests):
    menu["couple"]["arm"] = "middle"


@case("reserved_seat_outside_the_table", errors=[M + "field 'reservedSeats[0]' is not a seat of the table: it has 19 seats"])
def _(menu, guests):
    menu["reservedSeats"] = [20]


@case(
    "reserved_seat_taken_by_the_couple",
    errors=[M + "field 'couple.members[1].seat' refers to the seat 13, which is reserved ('reservedSeats')"],
)
def _(menu, guests):
    menu["couple"]["members"][1]["seat"] = 13


@case("unused_requirement", warnings=[M + "field 'requirements.eggs' is not used by any seat; it is left out of the legend"])
def _(menu, guests):
    menu["requirements"]["eggs"] = {"letter": "E", "label": "no eggs"}


@case("unused_allergen", warnings=[M + "field 'allergens.eggs' is not used by any dish or requirement"])
def _(menu, guests):
    menu["allergens"]["eggs"] = {"label": "eggs"}


@case("staff_texts_of_a_guest_section", warnings=[M + "field 'sections[5].staff' has no effect: the section is for the guests only"])
def _(menu, guests):
    menu["sections"][5]["staff"] = {"title": "Signature"}


@case(
    "drinks_note_of_a_staff_widget",
    warnings=[
        M + "field 'sections[4].widgets[1].note' has no effect: the note is shown to the guests, and the widget is "
        "for the staff only (the staff page shows 'staff.note')"
    ],
)
def _(menu, guests):
    menu["sections"][4]["widgets"][1]["note"] = "Ask the bar for cocktails"


@case("staff_note_of_a_guest_widget", warnings=[M + "field 'sections[4].widgets[0].staff' has no effect: the widget is for the guests only"])
def _(menu, guests):
    menu["sections"][4]["widgets"][0]["staff"] = {"note": "The bar mixes cocktails."}


@case("dish_for_the_staff_without_a_staff_widget", warnings=[M + "field 'dishes.melon' is not shown on any page"])
def _(menu, guests):
    del menu["sections"][2]["widgets"][1]


@case(
    "dish_without_allergens",
    warnings=[
        M + "field 'dishes.bruschetta.staff.allergens' is not set: the staff page shows no allergen information "
        "for the dish (write [] for none)"
    ],
)
def _(menu, guests):
    del menu["dishes"]["bruschetta"]["staff"]["allergens"]


@case(
    "missing_swap",
    warnings=[
        M + "field 'dishes.cheese-board.staff.swaps' has no swap for 'nuts', while the dish holds an allergen it "
        "avoids and 1 seat(s) need it"
    ],
)
def _(menu, guests):
    del menu["dishes"]["cheese-board"]["staff"]["swaps"]["nuts"]


@case("set_in_no_widget", warnings=[M + "field 'sets.meat' is not shown on any page"])
def _(menu, guests):
    menu["sections"][3]["widgets"][0]["items"] = ["fish"]
    menu["sets"]["fish"]["courses"] += ["carpaccio", "duck"]


# --------------------------------------------------------------------------
# Section part headings (the base `parts`: sections[2] is the
# food in two parts, sections[4] the texts under headings, its last part for
# the staff only)
# --------------------------------------------------------------------------


def food(menu: dict) -> list:
    return menu["sections"][2]["widgets"]


def info(menu: dict) -> list:
    return menu["sections"][4]["widgets"]


@case("heading_without_a_title", base="parts", errors=[M + "field 'sections[2].widgets[0].title' is required"])
def _(menu, guests):
    del food(menu)[0]["title"]


@case("heading_with_an_empty_title", base="parts",
      errors=[M + "field 'sections[2].widgets[0].title' must not be empty"])
def _(menu, guests):
    food(menu)[0]["title"] = " "


@case("heading_title_on_two_lines", base="parts",
      errors=[M + "field 'sections[2].widgets[3].title' must be a single line (no line breaks)"])
def _(menu, guests):
    food(menu)[3]["title"] = "Main\ncourse"


@case("heading_with_an_unknown_field", base="parts",
      errors=[M + "unknown field 'sections[2].widgets[0].subtitle' (did you mean 'title'?)"])
def _(menu, guests):
    food(menu)[0]["subtitle"] = "Shared plates"


@case("staff_texts_of_a_heading_with_an_unknown_field", base="parts",
      errors=[M + "unknown field 'sections[2].widgets[0].staff.note'"])
def _(menu, guests):
    food(menu)[0]["staff"]["note"] = "On the table by 19:15"


@case("token_in_a_heading", base="parts",
      errors=[M + "field 'sections[4].widgets[0].title' must not contain '{token}': menu pages hold no token"])
def _(menu, guests):
    info(menu)[0]["title"] = "Smoking {token}"


@case("staff_texts_of_a_heading_for_the_guests", base="parts",
      warnings=[M + "field 'sections[2].widgets[0].staff' has no effect: the widget is for the guests only"])
def _(menu, guests):
    food(menu)[0]["audience"] = "guest"


@case("heading_at_the_end_of_a_section", base="parts", warnings=[
    M + "field 'sections[4].widgets[4]' is a heading and the last widget of the section: nothing stands under the heading"])
def _(menu, guests):
    info(menu).pop()


@case("two_headings_in_a_row", base="parts", warnings=[
    M + "field 'sections[4].widgets[0]' is a heading followed by another heading: nothing stands under the heading"])
def _(menu, guests):
    del info(menu)[1]


# --------------------------------------------------------------------------
# The navigation bar labels
# --------------------------------------------------------------------------


@case("label_of_the_cover", base="parts", errors=[M + "unknown field 'sections[0].nav'"])
def _(menu, guests):
    menu["sections"][0]["nav"] = "Top"


@case("empty_label", base="parts", errors=[
    M + "field 'sections[2].nav' must not be empty: leave the field out for a section without a link in the "
    "navigation bar"])
def _(menu, guests):
    menu["sections"][2]["nav"] = " "


@case("label_on_two_lines", base="parts",
      errors=[M + "field 'sections[2].nav' must be a single line (no line breaks)"])
def _(menu, guests):
    menu["sections"][2]["nav"] = "Food\nand wine"


@case("label_that_is_no_text", base="parts", errors=[M + "field 'sections[3].nav' must be a string, got a boolean"])
def _(menu, guests):
    menu["sections"][3]["nav"] = True


@case("label_repeated", base="parts", warnings=[
    M + "field 'sections[4].nav' repeats the label of sections[2] in the navigation bar (letter case aside)"])
def _(menu, guests):
    menu["sections"][4]["nav"] = " FOOD"


@case("misspelt_heading_type", base="parts", errors=[
    M + "field 'sections[2].widgets[3].type' names an unknown widget type 'headng' (did you mean 'heading'?); "
    "known: text, seating, dishes, sets, drinks, heading"])
def _(menu, guests):
    food(menu)[3]["type"] = "headng"


# --------------------------------------------------------------------------
# guests.json
# --------------------------------------------------------------------------


@case(
    "reserved_seat_taken_by_a_record",
    errors=[G(8) + "field 'seats[0].number' refers to the seat 13, which is reserved ('reservedSeats')"],
)
def _(menu, guests):
    record(guests, "Timur")["seats"][0]["number"] = 13


@case("seat_not_at_the_table", errors=[G(3) + "field 'seats[0].number' is not a seat of the table: it has 19 seats"])
def _(menu, guests):
    record(guests, "Boris")["seats"][0]["number"] = 25


@case("seat_taken_twice", errors=[G(4) + "field 'seats[0].number' refers to the seat 4, already taken by guest #3"])
def _(menu, guests):
    record(guests, "Galina")["seats"][0]["number"] = 4


@case("seat_of_the_couple_taken", errors=[G(4) + "field 'seats[0].number' refers to the seat 6, already taken by the couple"])
def _(menu, guests):
    record(guests, "Galina")["seats"][0]["number"] = 6


@case(
    "more_seats_than_colours",
    base="mockup16",
    errors=[G(1) + "field 'seats' lists 4 seats, at most 3 are allowed: a guest page marks each of the "
            "record's seats in a colour of its own (split the record in two)"],
)
def _(menu, guests):
    record(guests, "Olga")["seats"] += [{"number": 12, "name": "Hugo"}, {"number": 13, "name": "Oscar"}]


@case(
    "seat_number_not_a_number",
    errors=[G(3) + "field 'seats[0].number' must be a positive whole number, got a string"],
)
def _(menu, guests):
    record(guests, "Boris")["seats"][0]["number"] = "4"


@case(
    "plus_one_on_the_first_seat",
    errors=[G(3) + "field 'seats[0].plusOne' cannot be set on the first seat: it is the guest's own seat"],
)
def _(menu, guests):
    record(guests, "Boris")["seats"][0]["plusOne"] = True


@case(
    "second_seat_without_a_name",
    errors=[G(5) + "field 'seats[1].name' is required for a seat that is not a +1 ('plusOne': true)"],
)
def _(menu, guests):
    del record(guests, "Olga")["seats"][1]["plusOne"]


@case(
    "unknown_requirement_of_a_seat",
    errors=[
        G(3) + "field 'seats[0].requirements[0]' refers to an unknown requirement (did you mean 'nuts'?); "
        "known: nuts, gluten, lactose, vegan, alcohol"
    ],
)
def _(menu, guests):
    record(guests, "Boris")["seats"][0]["requirements"] = ["nutz"]


@case(
    "more_dietary_notes_than_badges",
    errors=[G(6) + "field 'seats[0].requirements' needs 3 badges, seat 10 has room for 2"],
)
def _(menu, guests):
    record(guests, "Egor")["seats"][0]["requirements"].append("nuts")


@case("record_without_seats", errors=[G(4) + "field 'seats' must list at least one seat (the guest's own seat comes first)"])
def _(menu, guests):
    record(guests, "Galina")["seats"] = []


@case("record_without_a_name", errors=[G(4) + "field 'name' is required"])
def _(menu, guests):
    del record(guests, "Galina")["name"]


@case("record_with_an_empty_name", errors=[G(4) + "field 'name' must not be empty"])
def _(menu, guests):
    record(guests, "Galina")["name"] = " "


@case("unknown_field_named_like_a_person", errors=[G(4) + "unknown field '<unknown key>'"])
def _(menu, guests):
    record(guests, "Galina")["Olga"] = True


@case(
    "two_staff_records",
    errors=[G(14) + "is a second staff record (the first is guest #13); there may be only one"],
)
def _(menu, guests):
    guests.append({"token": "Second-staff-token-7Qx2", "staff": True})


@case(
    "staff_record_with_a_name",
    errors=[G(13) + "field 'name' is not allowed in the staff record: it has a token and nothing else"],
)
def _(menu, guests):
    guests[12]["name"] = "Waiter"


@case("staff_record_set_to_false", errors=[G(13) + "field 'staff' must be true (leave the field out for a guest)"])
def _(menu, guests):
    guests[12]["staff"] = False


@case(
    "token_repeated_in_another_case",
    errors=[
        G(4) + "duplicate token (same as guest #3; tokens are compared case-insensitively because they become "
        "directory names)"
    ],
)
def _(menu, guests):
    record(guests, "Galina")["token"] = "CRANE-7m2p"


@case(
    "reserved_token",
    errors=[
        G(4) + "'token' is a reserved name: its page directory would be the shared-files directory "
        "(letter case aside); choose another token"
    ],
)
def _(menu, guests):
    record(guests, "Galina")["token"] = "Assets"


@case(
    "short_staff_token",
    warnings=[
        G(13) + "field 'token' is shorter than 16 characters: the staff page shows every name and dietary note; "
        "use a random token of at least 16 characters"
    ],
)
def _(menu, guests):
    guests[12]["token"] = "kitchen-staff-1"


@case(
    "guest_switches_on_a_staff_section",
    errors=[G(3) + "field 'sections.kitchen' refers to a section for the staff only: a guest never sees it"],
)
def _(menu, guests):
    menu["sections"].append(kitchen_section())
    record(guests, "Boris")["sections"] = {"kitchen": {"visible": True}}


@case(
    "override_of_a_section_named_like_a_person",
    errors=[
        G(3) + "field 'sections.<unknown key>' refers to an unknown section; "
        "known: cover, seats, starters, main, drinks, signature"
    ],
)
def _(menu, guests):
    record(guests, "Boris")["sections"] = {"Olga": {"visible": False}}


@case("override_of_the_cover", errors=[G(3) + "field 'sections.cover' cannot be set: the cover is the same for everybody"])
def _(menu, guests):
    record(guests, "Boris")["sections"] = {"cover": {"visible": False}}


@case(
    "override_of_a_staff_widget",
    errors=[G(11) + "field 'sections.drinks.widgets.staff-list' refers to a widget for the staff only: a guest never sees it"],
)
def _(menu, guests):
    record(guests, "Gleb")["sections"]["drinks"] = {"widgets": {"staff-list": {"visible": False}}}


@case(
    "override_of_a_widget_without_an_id",
    errors=[
        G(3) + "field 'sections.starters.widgets.<unknown key>' refers to no widget of section 'starters'; "
        'give the widget an "id" in menu.json to address it'
    ],
)
def _(menu, guests):
    record(guests, "Boris")["sections"] = {"starters": {"widgets": {"Olga": {"visible": False}}}}


@case(
    "plus_one_not_next_to_the_guest",
    warnings=[G(5) + "field 'seats[1].number' is a +1 seat that is not next to the guest's own seat 8 on the table plan"],
)
def _(menu, guests):
    record(guests, "Olga")["seats"][1]["number"] = 5
    record(guests, "Galina")["seats"][0]["number"] = 9


@case("note_to_a_hidden_section", warnings=[G(3) + "field 'sections.main.note' is set, but the section is hidden for this guest"])
def _(menu, guests):
    record(guests, "Boris")["sections"] = {"main": {"visible": False, "note": "See you at the bar!"}}


# --------------------------------------------------------------------------
# Without a table
# --------------------------------------------------------------------------


@case("seat_beyond_the_largest_number", base="plain", errors=[G(1) + "field 'seats[0].number' must be at most 999"])
def _(menu, guests):
    record(guests, "Lev")["seats"][0]["number"] = 1000


@case(
    "seat_taken_twice_without_a_table",
    base="plain",
    errors=[G(3) + "field 'seats[0].number' refers to a seat, already taken by guest #1"],
)
def _(menu, guests):
    record(guests, "Rita")["seats"][0]["number"] = 1


@case(
    "reserved_seats_without_a_table",
    base="plain",
    warnings=[M + "field 'reservedSeats' has no effect without 'table': only a table plan shows free seats"],
)
def _(menu, guests):
    # a guest's seat: the list has no effect, so that is no error either
    menu["reservedSeats"] = [1]


@case(
    "couple_label_without_a_table",
    base="plain",
    warnings=[M + "field 'couple.label' has no effect without 'table'"],
)
def _(menu, guests):
    menu["couple"] = {"label": fixtures.COUPLE_LABEL, "members": [{"seat": 5, "name": "Vera"}, {"seat": 6, "name": "Ivan"}]}


@case("three_members_of_the_couple", base="plain", errors=[M + "field 'couple.members' must list one or two members"])
def _(menu, guests):
    menu["couple"] = {"members": [{"seat": 5, "name": "Vera"}, {"seat": 6, "name": "Ivan"}, {"seat": 7, "name": "Olga"}]}


# --------------------------------------------------------------------------
# The language and the words of the pages
# --------------------------------------------------------------------------

LANG_PROBLEM = "field 'lang' must be a language tag such as 'en', 'de' or 'sr-Latn'"


@case("language_tag_with_an_underscore", errors=[M + LANG_PROBLEM])
def _(menu, guests):
    menu["lang"] = "sr_Latn"


@case("language_tag_of_the_wrong_type", errors=[M + LANG_PROBLEM])
def _(menu, guests):
    menu["lang"] = ["en"]


@case("empty_language_tag", errors=[M + LANG_PROBLEM])
def _(menu, guests):
    menu["lang"] = ""


@case("misspelt_word", errors=[M + "unknown field 'strings.sectoins' (did you mean 'sections'?)"])
def _(menu, guests):
    menu["strings"] = {"sectoins": "Parts"}


@case("empty_word", errors=[M + "field 'strings.pageTitle' must not be empty"])
def _(menu, guests):
    menu["strings"] = {"pageTitle": " "}


@case("word_on_two_lines", errors=[M + "field 'strings.staffVersion' must be a single line (no line breaks)"])
def _(menu, guests):
    menu["strings"] = {"staffVersion": "Staff version\nnot for guests"}


@case("word_with_template_syntax",
      errors=[M + "field 'strings.you' must not contain '{{' or '}}' (menu texts have no template syntax)"])
def _(menu, guests):
    menu["strings"] = {"you": "{{you}}"}


@case("pattern_without_its_placeholder", errors=[M + "field 'strings.guestOf' must contain the placeholder {name}"])
def _(menu, guests):
    menu["strings"] = {"guestOf": "a guest"}


@case(
    "pattern_with_an_unknown_placeholder",
    errors=[M + "field 'strings.tablePlan' has an unknown placeholder {tabel}; known: {table}, {seats}, {yours}, {colours}"],
)
def _(menu, guests):
    menu["strings"] = {"tablePlan": "{tabel} {table}: {seats}. {yours}: {colours}"}


@case("plural_form_without_the_number", errors=[M + "field 'strings.seatCount.one' must contain the placeholder {n}"])
def _(menu, guests):
    menu["strings"] = {"seatCount": {"one": "one seat", "other": "{n} seats"}}


@case("plural_word_of_the_wrong_type", errors=[M + "field 'strings.noteCount' must be an object, got a string"])
def _(menu, guests):
    menu["strings"] = {"noteCount": "{n} notes"}


@case("colour_names_of_the_wrong_count", errors=[M + "field 'strings.seatColours' must be a list of 3 strings"])
def _(menu, guests):
    menu["strings"] = {"seatColours": ["blue", "red"]}


@case("empty_colour_name", errors=[M + "field 'strings.seatColours[1]' must be a non-empty single-line string"])
def _(menu, guests):
    menu["strings"] = {"seatColours": ["blue", "", "green"]}


class BrokenDataTest(unittest.TestCase):
    """One test per broken copy (`CASES`), added below the class."""

    def run_case(self, item: Case) -> None:
        menu, guests = fixtures.SETS[item.base]()
        item.change(menu, guests)
        errors, warnings = full_check(menu, guests)
        self.assertEqual((errors, warnings), (item.errors, item.warnings))
        secrets = secrets_of(menu, guests) | secrets_of(*fixtures.SETS[item.base]())
        for message in errors + warnings:
            for secret in secrets:
                self.assertNotIn(secret, message)

    def test_every_case_changes_one_thing_and_gives_one_message(self):
        for item in CASES:
            with self.subTest(case=item.name):
                self.assertEqual(len(item.errors) + len(item.warnings), 1)

    def test_case_names_are_unique(self):
        names = [item.name for item in CASES]
        self.assertEqual(len(names), len(set(names)))


def _case_test(item: Case) -> Callable:
    def test(self: BrokenDataTest) -> None:
        self.run_case(item)
    test.__doc__ = f"broken copy: {item.name.replace('_', ' ')}"
    return test


for _item in CASES:
    setattr(BrokenDataTest, f"test_{_item.name}", _case_test(_item))


# --------------------------------------------------------------------------
# The fixtures and what the index learns
# --------------------------------------------------------------------------


FREE_SEATS_12_13 = (
    M + "field 'table.seats' has 2 free seat(s): 12, 13 (shown as free on the staff page; "
    "list a seat that stays free on purpose in 'reservedSeats')"
)


class FixturesTest(unittest.TestCase):
    def test_fixtures_pass(self):
        expected = {"mockup16": [FREE_SEATS_12_13], "reserved19": [], "plain": [], "parts": []}
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                index, errors, warnings = check(*make())
                self.assertEqual(errors, [])
                self.assertEqual(warnings, expected[name])
                self.assertTrue(index.ok)

    def test_index_of_reserved19(self):
        index, _errors, _warnings = check(*fixtures.reserved19())
        self.assertTrue(index.table_ok)
        self.assertEqual(index.total, 19)
        self.assertEqual(index.seats, 19)
        self.assertEqual(index.reserved, {13: 0})
        self.assertEqual(index.couple_seats, {6: 0, 7: 1})
        self.assertEqual(index.guests, 12)
        self.assertEqual(index.staff_record, 13)
        self.assertEqual(sorted(index.taken), [n for n in range(1, 20) if n != 13])
        self.assertEqual(index.taken[1], "guest #1")
        self.assertEqual(index.taken[19], "guest #1")
        self.assertEqual(index.seat_requirements[10], ["gluten", "lactose"])
        self.assertEqual(index.seat_requirements[7], ["gluten"])

    def test_without_a_table_the_seats_are_the_taken_ones(self):
        index, _errors, _warnings = check(*fixtures.plain())
        self.assertFalse(index.has_table)
        self.assertIsNone(index.total)
        self.assertEqual(index.seats, 4)

    def test_reserved_seats_give_no_free_seat_warning(self):
        menu, guests = fixtures.mockup16()
        menu["reservedSeats"] = [12, 13]
        self.assertEqual(check(menu, guests)[1:], ([], []))
        menu["reservedSeats"] = [13]
        warning = (
            M + "field 'table.seats' has 1 free seat(s): 12 (shown as free on the staff page; "
            "list a seat that stays free on purpose in 'reservedSeats')"
        )
        self.assertEqual(check(menu, guests)[1:], ([], [warning]))

    def test_a_plus_one_across_the_end_of_the_numbers_is_next_to_the_guest(self):
        menu, guests = fixtures.reserved19()
        self.assertEqual(record(guests, "Greta")["seats"], [{"number": 19}, {"number": 1, "plusOne": True, "name": "Hugo"}])
        self.assertEqual(check(menu, guests)[1:], ([], []))
        # the same +1 two seats away is not
        record(guests, "Greta")["seats"][1]["number"] = 2
        record(guests, "Peggy and Victor")["seats"][0]["number"] = 1
        warning = G(1) + "field 'seats[1].number' is a +1 seat that is not next to the guest's own seat 19 on the table plan"
        self.assertEqual(check(menu, guests)[1:], ([], [warning]))

    def test_derived_warnings_wait_for_the_errors(self):
        # a seat moved by mistake leaves its seat free and its note unused:
        # only the error is reported
        menu, guests = fixtures.reserved19()
        record(guests, "Boris")["seats"][0]["number"] = 25
        _index, errors, warnings = check(menu, guests)
        self.assertEqual(len(errors), 1)
        self.assertEqual(warnings, [])

    def test_no_staff_record(self):
        menu, guests = fixtures.reserved19()
        del guests[12]
        self.assertEqual(
            check(menu, guests)[1:],
            (
                [],
                [
                    "guests.json: has no staff record ('staff': true): no staff page is built",
                    M + "field 'sections' has parts for the staff only (sections[2].widgets[1], "
                    "sections[4].widgets[1]), but there is no staff record",
                ],
            ),
        )

    def test_staff_record_without_a_token(self):
        menu, guests = fixtures.reserved19()
        del guests[12]["token"]
        self.assertEqual(check(menu, guests)[1:], ([G(13) + "field 'token' is required"], []))

    def test_labels_of_the_line_on_any_section_but_the_cover(self):
        # a section for the staff or for the guests only may have a label:
        # the page that shows it links it
        menu, guests = fixtures.parts()
        menu["sections"].insert(4, {**kitchen_section(), "nav": "Kitchen"})
        menu["sections"][-1]["nav"] = "Thanks"
        self.assertEqual(full_check(menu, guests), ([], []))
        # the same label once in lower case and once in upper case: one warning
        menu["sections"][-1]["nav"] = "kitchen"
        self.assertEqual(full_check(menu, guests), ([], [
            M + "field 'sections[6].nav' repeats the label of sections[4] in the navigation bar "
            "(letter case aside)"]))


# --------------------------------------------------------------------------
# Messages of the table module, documents of the wrong shape
# --------------------------------------------------------------------------


def row_table() -> dict:
    """A row of 7 squeezed seats along the top edge of the field."""
    return {
        "label": "Row",
        "arms": [{"id": "main", "x": 40, "y": 56, "width": 238, "height": 30}],
        "seats": [{"arm": "main", "side": "top", "count": 7}],
    }


class TableMessagesTest(unittest.TestCase):
    def test_couple_label_on_the_spot_of_a_label_of_a_guest(self):
        # the couple label is on the staff plan, the label "You" on a guest's
        # plan: one may take the other's spot
        menu, guests = fixtures.plain()
        menu["table"] = row_table()
        menu["couple"] = {"label": fixtures.COUPLE_LABEL, "members": [{"seat": 4, "name": "Vera"}]}
        record(guests, "Rita")["seats"][0]["number"] = 5
        _index, errors, warnings = check(menu, guests)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [
            M + "table.arms[0] side 'top': seats 1-7 squeezed closer than 42 px",
            M + "field 'table.seats' has 2 free seat(s): 6, 7 (shown as free on the staff page; list a seat "
            "that stays free on purpose in 'reservedSeats')",
        ])
        self.assertEqual(full_check(menu, guests)[0], [])

    def test_the_couple_against_a_table(self):
        menu, guests = fixtures.reserved19()
        menu["couple"]["members"].append({"seat": 13, "name": "Olga"})
        errors = check(menu, guests)[1]
        self.assertEqual(errors, [M + "couple.members[].seat: expected 1-2 different seat numbers from 1 to 19"])

    def test_dietary_notes_of_the_couple_need_badges_too(self):
        menu, guests = fixtures.reserved19()
        menu["couple"]["members"][1]["requirements"] = ["nuts", "gluten", "lactose"]
        errors = check(menu, guests)[1]
        self.assertEqual(errors, [M + "field 'couple.members[1].requirements' needs 3 badges, seat 7 has room for 2"])

    def test_a_table_with_aligned_seats(self):
        menu, guests = fixtures.reserved19()
        # seat 8 faces seat 1, seats 14 and 15 inside the short arm face seats 12 and 11
        menu["table"]["seats"][2]["align"] = [1, None, None, None, None]
        menu["table"]["seats"][4]["align"] = [12, 11]
        index, errors, warnings = check(menu, guests)
        self.assertEqual((errors, warnings), ([], []))
        self.assertTrue(index.table_ok)
        self.assertEqual(index.total, 19)

    def test_a_broken_table_still_counts_its_seats(self):
        menu, guests = fixtures.reserved19()
        menu["table"]["arms"][0]["width"] = "wide"
        index, errors, _warnings = check(menu, guests)
        self.assertEqual(errors, [M + "table.arms[0].width: expected an integer (px)"])
        self.assertFalse(index.table_ok)
        self.assertEqual(index.total, 19)

    def test_top_level_values_of_the_wrong_type(self):
        report = _core.Report()
        index = _schema.check_data([], [], report)
        self.assertEqual(report.errors, [M + "the top-level value must be an object, got an array"])
        self.assertFalse(index.version_ok)
        menu, _guests = fixtures.reserved19()
        self.assertEqual(
            check(menu, {})[1],
            ["guests.json: the top-level value must be an array of records, got an object"],
        )
        self.assertEqual(check(menu, [])[1:], ([], ["guests.json: contains no records"]))
        self.assertEqual(check(menu, ["Olga"])[1][0], G(1) + "must be an object, got a string")

    def test_a_key_repeated_in_guests_json_is_not_shown(self):
        menu, guests = fixtures.reserved19()
        index = check(menu, guests)[0]
        text = (
            '[{"token": "heron-4tx9", "name": "Olga", "seats": [{"number": 8}],'
            ' "sections": {"Olga": {}, "Olga": {}, "main": {"note": "a", "note": "b"}}}]'
        )
        with tempfile.TemporaryDirectory(prefix="menu-schema-test-") as temporary:
            path = Path(temporary) / "guests.json"
            path.write_text(text, encoding="utf-8")
            report = _core.Report()
            value = _core.read_json(path, report, _schema.guest_known(index))
        self.assertIs(value, _core.MISSING)
        self.assertEqual(len(report.errors), 2)
        self.assertTrue(report.errors[0].endswith(
            "duplicate key <unknown key> in '[0].sections' (JSON keeps only the last one; merge or rename them)"
        ))
        self.assertTrue(report.errors[1].endswith("duplicate key 'note' in '[0].sections.main' (JSON keeps only the last one; merge or rename them)"))
        for message in report.errors:
            self.assertNotIn("Olga", message)


class LanguageTest(unittest.TestCase):
    """`lang` and `strings` beyond the one-message cases."""

    def test_an_english_menu_may_give_some_words(self):
        for tag in ("en", "en-GB", "EN-us"):
            with self.subTest(lang=tag):
                menu, guests = fixtures.reserved19()
                menu.update(lang=tag, strings={"and": "and", "seatInline": "place", "seatsInline": "places",
                                               "guestCount": {"one": "{n} diner", "other": "{n} diners"}})
                self.assertEqual(full_check(menu, guests), ([], []))

    def test_every_english_word_given_as_the_menu_word(self):
        menu, guests = fixtures.reserved19()
        menu["strings"] = {key: list(value) if isinstance(value, tuple) else value
                           for key, value in _words.ENGLISH.items()}
        self.assertEqual(full_check(menu, guests), ([], []))
        # a language of the same plural rule takes them as they are
        menu["lang"] = "de"
        self.assertEqual(full_check(menu, guests), ([], []))

    def test_labels_of_the_line_are_compared_with_their_case_folded(self):
        menu, guests = fixtures.parts()
        menu["sections"][3]["nav"] = "Straße"
        menu["sections"][4]["nav"] = "STRASSE"
        self.assertEqual(full_check(menu, guests), ([], [
            M + "field 'sections[4].nav' repeats the label of sections[3] in the navigation bar "
            "(letter case aside)"]))


class UsageTest(unittest.TestCase):
    """`check_usage` on hand-made usage sets."""

    def usage(self, **changes) -> SimpleNamespace:
        menu, _guests = fixtures.reserved19()
        dishes = set(menu["dishes"])
        usage = SimpleNamespace(
            dishes=dishes, sets=set(menu["sets"]), drinks=set(menu["drinks"]["items"]), staff_dishes=set(dishes)
        )
        for key, value in changes.items():
            setattr(usage, key, value)
        return usage

    def warnings(self, menu, guests, usage) -> list[str]:
        index = check(menu, guests)[0]
        report = _core.Report()
        _schema.check_usage(index, menu, usage, report)
        self.assertEqual(report.errors, [])
        return report.warnings

    def test_everything_shown(self):
        self.assertEqual(self.warnings(*fixtures.reserved19(), self.usage()), [])

    def test_parts_no_page_shows(self):
        usage = self.usage(dishes={"hummus"}, sets={"fish"}, drinks={"fizz"})
        warnings = self.warnings(*fixtures.reserved19(), usage)
        self.assertIn(M + "field 'dishes.melon' is not shown on any page", warnings)
        self.assertIn(M + "field 'sets.meat' is not shown on any page", warnings)
        self.assertIn(M + "field 'drinks.items.juice' is not shown on any page", warnings)
        self.assertEqual(len(warnings), 7 + 1 + 4)

    def test_a_dish_of_the_staff_page_without_allergens(self):
        menu, guests = fixtures.reserved19()
        del menu["dishes"]["hummus"]["staff"]["allergens"]
        self.assertEqual(
            self.warnings(menu, guests, self.usage()),
            [
                M + "field 'dishes.hummus.staff.allergens' is not set: the staff page shows no allergen "
                "information for the dish (write [] for none)"
            ],
        )
        # a dish the staff page does not show needs none
        self.assertEqual(self.warnings(menu, guests, self.usage(staff_dishes={"melon"})), [])

    def test_a_missing_swap(self):
        menu, guests = fixtures.reserved19()
        del menu["dishes"]["cheese-board"]["staff"]["swaps"]["nuts"]
        self.assertEqual(
            self.warnings(menu, guests, self.usage()),
            [
                M + "field 'dishes.cheese-board.staff.swaps' has no swap for 'nuts', while the dish holds an "
                "allergen it avoids and 1 seat(s) need it"
            ],
        )

    def test_without_allergens_nothing_is_said_about_them(self):
        menu, guests = fixtures.plain()
        index = check(menu, guests)[0]
        report = _core.Report()
        usage = SimpleNamespace(
            dishes=set(menu["dishes"]), sets=set(menu["sets"]), drinks=set(menu["drinks"]["items"]),
            staff_dishes=set(menu["dishes"]),
        )
        _schema.check_usage(index, menu, usage, report)
        self.assertEqual((report.errors, report.warnings), ([], []))


if __name__ == "__main__":
    unittest.main()
