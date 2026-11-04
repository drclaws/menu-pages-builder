"""Fictional menu data for the tests: four sets of `menu.json` and `guests.json`.

Each function returns a fresh `(menu, guests)` pair that a test may change.

* `mockup16` - the design mockup's menu: an L-shaped table of 16 seats,
  a legend of five dietary notes, five shared starters, two sets of two
  courses, four drinks; a +1 without a name (seats 8-9), the couple at 4-5,
  seats 12 and 13 free.
* `reserved19` - an L-shaped table of 19 seats with one seat kept free at the
  end of the short arm and the couple side by side on the outer side of the
  long arm by the joint; three starters and one more dish on request for the
  staff only; two sets (fish and meat); sparkling, white and red wine and
  soft drinks with a note for the guests.  The records: a guest on the last
  seat with a +1 on seat 1, a record for two, a +1 without a name and one
  with a name, seats with dietary notes (one with two), a note on a section,
  a hidden widget and the staff record.
* `plain` - no table, no dietary notes, no allergens; three sets, one
  category of drinks, three records (one with a +1) and the staff record.
* `parts` - `reserved19` with the starters and the main course in one
  section of two parts under their headings (the staff page has its own
  eyebrows) and a section of short texts under headings after the drinks,
  its last part for the staff only; the seats, the food, the drinks and the
  texts have labels in the navigation bar, the signature has none.
* `serbian` - `reserved19` in Serbian, in the Latin script ("lang":
  "sr-Latn"): every word of the pages in `strings` (plural forms one, few
  and other), the texts of the menu and the names with diacritics (č ć đ š
  ž), the badge letters Č and Ž.

The dietary notes name what to leave out ("no nuts"), never a reason.  The
Serbian texts are fictional too.
"""

import copy
import json
from pathlib import Path

COUPLE_NAMES = "Ivan & Vera"
EVENT = {
    "title": "Anniversary dinner",
    "when": "15 June 2030, 19:00",
    "place": "Riverside Bistro · Example Street 5",
}
COUPLE_LABEL = "Ivan · Vera"

REQUIREMENTS = {
    "nuts": {"letter": "N", "label": "no nuts", "avoids": ["nuts"]},
    "gluten": {"letter": "G", "label": "no gluten", "avoids": ["gluten"]},
    "lactose": {"letter": "L", "label": "no lactose", "avoids": ["lactose"]},
    "vegan": {"letter": "V", "label": "vegan"},
    "alcohol": {"letter": "A", "label": "no alcohol"},
}
ALLERGENS = {
    "nuts": {"label": "nuts"},
    "gluten": {"label": "gluten"},
    "lactose": {"label": "lactose"},
}

#: The staff texts, the same in every set.
STAFF = {
    "updated": "12 June 2030",
    "contact": "Selma (event planner) · +00 000 000 00 00",
    "reminder": "Staff link only — please do not show this page to guests.",
}


def l_table_16() -> dict:
    """The mockup's L-shaped table of 16 seats."""
    return {
        "label": "L-shaped table",
        "arms": [
            {"id": "top", "x": 40, "y": 60, "width": 200, "height": 52},
            {"id": "right", "x": 188, "y": 60, "width": 52, "height": 200},
        ],
        "seats": [
            {"arm": "top", "side": "left"},                  # 1
            {"arm": "top", "side": "top", "count": 5},       # 2-6
            {"arm": "right", "side": "right", "count": 4},   # 7-10
            {"arm": "right", "side": "bottom"},              # 11
            {"arm": "right", "side": "left", "count": 2},    # 12-13
            {"arm": "top", "side": "bottom", "count": 3},    # 14-16
        ],
    }


def l_table_19() -> dict:
    """An L-shaped table of 19 seats: the long arm along the top, the short
    one down the right; every side keeps the full pitch of 42 px."""
    return {
        "label": "L-shaped table",
        "arms": [
            {"id": "long", "x": 39, "y": 40, "width": 240, "height": 52},
            {"id": "short", "x": 227, "y": 40, "width": 52, "height": 210},
        ],
        "seats": [
            {"arm": "long", "side": "left"},                 # 1
            {"arm": "long", "side": "top", "count": 6},      # 2-7
            {"arm": "short", "side": "right", "count": 5},   # 8-12
            {"arm": "short", "side": "bottom"},              # 13
            {"arm": "short", "side": "left", "count": 2},    # 14-15
            {"arm": "long", "side": "bottom", "count": 4},   # 16-19
        ],
    }


# --------------------------------------------------------------------------
# mockup16
# --------------------------------------------------------------------------

_MOCKUP16_MENU = {
    "schemaVersion": 1,
    "coupleNames": COUPLE_NAMES,
    "event": EVENT,
    "staff": STAFF,
    "requirements": REQUIREMENTS,
    "allergens": ALLERGENS,
    "couple": {
        "label": COUPLE_LABEL,
        "members": [
            {"seat": 4, "name": "Vera", "role": "host"},
            {"seat": 5, "name": "Ivan", "role": "host"},
        ],
    },
    "table": l_table_16(),
    "dishes": {
        "beet-tartare": {
            "name": "Beetroot tartare",
            "ingredients": "Beetroot, walnuts, rye crisp",
            "staff": {
                "allergens": ["nuts", "gluten"],
                "swaps": {
                    "nuts": "serve the nut-free version on a separate plate",
                    "gluten": "serve it without the rye crisp",
                },
            },
        },
        "burrata": {
            "name": "Burrata with tomatoes",
            "ingredients": "Burrata, heirloom tomatoes, basil",
            "staff": {"allergens": ["lactose"], "swaps": {"lactose": "serve the tomatoes without burrata"}},
        },
        "grilled-veg": {
            "name": "Grilled vegetables",
            "ingredients": "Courgette, pepper, herb oil",
            "staff": {"allergens": [], "tags": ["vegan", "gluten-free"]},
        },
        "trout-rye": {
            "name": "Smoked trout on rye",
            "ingredients": "Trout, rye bread, dill",
            "staff": {"allergens": ["gluten"], "swaps": {"gluten": "serve on cucumber slices instead of rye"}},
        },
        "olives": {
            "name": "Marinated olives",
            "ingredients": "Olives, lemon, thyme",
            "staff": {"allergens": []},
        },
        "salmon-tartare": {
            "name": "Salmon tartare",
            "ingredients": "Salmon, avocado, sour cream",
            "staff": {"allergens": ["lactose"], "swaps": {"lactose": "serve the first course without sour cream"}},
        },
        "sea-bass": {
            "name": "Sea bass with a pistachio crust",
            "ingredients": "Sea bass, pistachios, spinach",
            "staff": {"allergens": ["nuts"], "swaps": {"nuts": "serve the second course without the crust"}},
        },
        "carpaccio": {
            "name": "Beef carpaccio",
            "ingredients": "Beef, rocket, croutons",
            "staff": {"allergens": ["gluten"], "swaps": {"gluten": "serve the first course without croutons"}},
        },
        "lamb": {
            "name": "Lamb with root vegetables",
            "ingredients": "Lamb, carrot, parsnip, jus",
            "staff": {"allergens": [], "swaps": {"vegan": "serve the roasted roots with lentils instead"}},
        },
    },
    "sets": {
        "a": {
            "title": "Set A",
            "hint": "Fish",
            "eyebrow": "two courses",
            "courses": ["salmon-tartare", "sea-bass"],
            "pairing": "white wine — see Wines",
        },
        "b": {
            "title": "Set B",
            "hint": "Meat",
            "eyebrow": "two courses",
            "courses": ["carpaccio", "lamb"],
            "pairing": "red wine — see Wines",
        },
    },
    "drinks": {
        "categories": {
            "sparkling": {"label": "Sparkling"},
            "white": {"label": "White"},
            "red": {"label": "Red"},
            "soft": {"label": "Soft"},
        },
        "items": {
            "fizz": {
                "category": "sparkling",
                "name": "Example Brut, Riverside Cellars",
                "details": "Example Valley · Chardonnay",
                "servedWith": "with the starters",
                "staff": {"bottles": "6 bottles", "serving": "from 19:00, well chilled", "swaps": {"alcohol": "no alcohol"}},
            },
            "white": {
                "category": "white",
                "name": "Example White, Hillside Estate",
                "details": "Example Coast · Sauvignon Blanc",
                "servedWith": "with Set A",
                "staff": {"bottles": "4 bottles", "serving": "8-10 °C"},
            },
            "red": {
                "category": "red",
                "name": "Example Red, Old Mill Winery",
                "details": "Example Hills · Pinot Noir",
                "servedWith": "with Set B",
                "staff": {"bottles": "4 bottles", "serving": "open by 18:30"},
            },
            "soft": {
                "category": "soft",
                "name": "Still and sparkling water, lemonade, apple juice, tea and coffee",
                "staff": {"serving": "water on the table from the start; tea and coffee after the main course"},
            },
        },
    },
    "sections": [
        {"id": "cover", "type": "cover"},
        {
            "id": "seats",
            "widgets": [
                {
                    "type": "seating",
                    "staff": {"footnote": "Every guest picks Set A or Set B at the table: take the orders after the starters."},
                }
            ],
        },
        {
            "id": "starters",
            "title": "Starters",
            "eyebrow": "Shared plates for the table",
            "staff": {"eyebrow": "Shared plates · on the table by 19:15"},
            "widgets": [{"type": "dishes", "items": ["beet-tartare", "burrata", "grilled-veg", "trout-rye", "olives"]}],
        },
        {
            "id": "main",
            "title": "Main course",
            "eyebrow": "Choose one of two sets",
            "staff": {"eyebrow": "Two sets · guests choose at the table"},
            "widgets": [
                {"type": "sets", "items": ["a", "b"], "note": "Your waiter will take your choice after the starters."},
                {
                    "type": "text",
                    "id": "allergy-card",
                    "audience": "guest",
                    "variant": "card",
                    "text": "Something you do not eat? Just tell your waiter: the kitchen will adjust the dishes.",
                },
            ],
        },
        {
            "id": "drinks",
            "title": "Drinks",
            "staff": {"eyebrow": "What to serve and when"},
            "widgets": [
                {
                    "type": "drinks",
                    "audience": "guest",
                    "groups": [
                        {"title": "Soft drinks", "layout": "inline", "items": ["soft"]},
                        {"title": "Wines", "layout": "list", "items": ["fizz", "white", "red"]},
                    ],
                },
                {
                    "type": "drinks",
                    "id": "staff-list",
                    "audience": "staff",
                    "groups": [{"layout": "list", "items": ["fizz", "white", "red", "soft"]}],
                },
            ],
        },
        {
            "id": "signature",
            "title": "Enjoy the evening!",
            "audience": "guest",
            "widgets": [{"type": "text", "variant": "signature", "text": COUPLE_NAMES}],
        },
    ],
}

_MOCKUP16_GUESTS = [
    {"token": "heron-4tx9", "name": "Olga", "seats": [{"number": 8}, {"number": 9, "plusOne": True}]},
    {"token": "crane-7m2p", "name": "Boris", "seats": [{"number": 3, "requirements": ["nuts"]}]},
    {"token": "lark-3vk8", "name": "Alyona", "seats": [{"number": 1, "requirements": ["alcohol"]}]},
    {"token": "finch-9ad4", "name": "Galina", "seats": [{"number": 2}]},
    {
        "token": "robin-2hx6",
        "name": "Gleb",
        "seats": [{"number": 6}],
        "sections": {"main": {"widgets": {"allergy-card": {"visible": False}}}},
    },
    {"token": "wren-5tc3", "name": "Zhanna", "seats": [{"number": 7, "requirements": ["vegan"]}]},
    {"token": "swift-8np2", "name": "Egor", "seats": [{"number": 10, "requirements": ["gluten", "lactose"]}]},
    {
        "token": "kite-4mz7",
        "name": "Timur",
        "seats": [{"number": 11}],
        "sections": {"signature": {"note": "Thank you for coming all the way from the coast!"}},
    },
    {"token": "owl-6rb9", "name": "Marta", "seats": [{"number": 14, "requirements": ["lactose"]}]},
    {
        "token": "stork-3jw5",
        "name": "Nina",
        "seats": [{"number": 15}, {"number": 16, "plusOne": True, "name": "Oscar"}],
    },
    {"token": "Hq7tLw2RzX9pVb4MkN6sYd", "staff": True},
]


def mockup16() -> tuple[dict, list]:
    """The mockup: 16 seats, seats 12 and 13 free."""
    return copy.deepcopy(_MOCKUP16_MENU), copy.deepcopy(_MOCKUP16_GUESTS)


# --------------------------------------------------------------------------
# reserved19
# --------------------------------------------------------------------------

_RESERVED19_MENU = {
    "schemaVersion": 1,
    "coupleNames": COUPLE_NAMES,
    "event": EVENT,
    "staff": STAFF,
    "requirements": REQUIREMENTS,
    "allergens": ALLERGENS,
    "couple": {
        "label": COUPLE_LABEL,
        "members": [
            {"seat": 6, "name": "Vera", "role": "host"},
            {"seat": 7, "name": "Ivan", "role": "host", "requirements": ["gluten"]},
        ],
    },
    "reservedSeats": [13],
    "table": l_table_19(),
    "dishes": {
        "bruschetta": {
            "name": "Tomato bruschetta",
            "ingredients": "Sourdough, tomatoes, basil",
            "staff": {"allergens": ["gluten"], "swaps": {"gluten": "serve the tomatoes on cucumber slices"}},
        },
        "cheese-board": {
            "name": "Cheese board",
            "ingredients": "Three cheeses, honey, walnuts",
            "staff": {
                "allergens": ["lactose", "nuts"],
                "swaps": {
                    "lactose": "bring the fruit plate instead",
                    "nuts": "serve a portion without walnuts on a separate plate",
                },
            },
        },
        "hummus": {
            "name": "Hummus with vegetables",
            "ingredients": "Chickpeas, tahini, carrot, cucumber",
            "staff": {"allergens": [], "tags": ["vegan", "gluten-free"]},
        },
        "melon": {
            "name": "Melon with mint",
            "ingredients": "Melon, mint, lime",
            "staff": {"allergens": [], "note": "Only when a guest asks for something else"},
        },
        "salmon": {
            "name": "Cured salmon",
            "ingredients": "Salmon, dill, sour cream",
            "staff": {"allergens": ["lactose"], "swaps": {"lactose": "serve the first course without sour cream"}},
        },
        "cod": {
            "name": "Baked cod with an almond crust",
            "ingredients": "Cod, almonds, spinach",
            "staff": {"allergens": ["nuts"], "swaps": {"nuts": "serve the second course without the crust"}},
        },
        "carpaccio": {
            "name": "Beef carpaccio",
            "ingredients": "Beef, rocket, croutons",
            "staff": {"allergens": ["gluten"], "swaps": {"gluten": "serve the first course without croutons"}},
        },
        "duck": {
            "name": "Duck with root vegetables",
            "ingredients": "Duck, carrot, parsnip, jus",
            "staff": {"allergens": [], "swaps": {"vegan": "serve the roasted roots with lentils instead"}},
        },
    },
    "sets": {
        "fish": {
            "title": "Set A",
            "hint": "Fish",
            "eyebrow": "two courses",
            "courses": ["salmon", "cod"],
            "pairing": "white wine",
        },
        "meat": {
            "title": "Set B",
            "hint": "Meat",
            "eyebrow": "two courses",
            "courses": ["carpaccio", "duck"],
            "pairing": "red wine",
        },
    },
    "drinks": {
        "categories": {
            "sparkling": {"label": "Sparkling"},
            "white": {"label": "White"},
            "red": {"label": "Red"},
            "soft": {"label": "Soft"},
        },
        "items": {
            "fizz": {
                "category": "sparkling",
                "name": "Example Brut, Riverside Cellars",
                "details": "Example Valley · Chardonnay",
                "servedWith": "with the starters",
                "staff": {"bottles": "6 bottles", "serving": "well chilled", "swaps": {"alcohol": "alcohol-free sparkling"}},
            },
            "white": {
                "category": "white",
                "name": "Example White, Hillside Estate",
                "details": "Example Coast · Sauvignon Blanc",
                "servedWith": "with Set A",
                "staff": {"bottles": "4 bottles"},
            },
            "red": {
                "category": "red",
                "name": "Example Red, Old Mill Winery",
                "details": "Example Hills · Pinot Noir",
                "servedWith": "with Set B",
                "staff": {"bottles": "4 bottles", "serving": "open by 18:30"},
            },
            "water": {"category": "soft", "name": "Still and sparkling water"},
            "juice": {
                "category": "soft",
                "name": "Lemonade and apple juice",
                "staff": {"serving": "jugs on the table from 19:00"},
            },
        },
    },
    "sections": [
        {"id": "cover", "type": "cover"},
        {
            "id": "seats",
            "widgets": [
                {
                    "type": "seating",
                    "staff": {"footnote": "Seat 13 stays free all evening: keep its place setting."},
                }
            ],
        },
        {
            "id": "starters",
            "title": "Starters",
            "eyebrow": "Shared plates for the table",
            "staff": {"eyebrow": "Shared plates · on the table by 19:15"},
            "widgets": [
                {"type": "dishes", "items": ["bruschetta", "cheese-board", "hummus"]},
                {"type": "dishes", "audience": "staff", "title": "On request", "items": ["melon"]},
            ],
        },
        {
            "id": "main",
            "title": "Main course",
            "eyebrow": "Choose one of two sets",
            "staff": {"eyebrow": "Two sets · guests choose at the table"},
            "widgets": [
                {
                    "type": "sets",
                    "items": ["fish", "meat"],
                    "note": "Your waiter will take your choice after the starters.",
                    "staff": {"note": "Take the orders once the starters are on the table."},
                },
                {
                    "type": "text",
                    "id": "allergy-card",
                    "audience": "guest",
                    "variant": "card",
                    "text": "Something you do not eat? Just tell your waiter: the kitchen will adjust the dishes.",
                },
            ],
        },
        {
            "id": "drinks",
            "title": "Drinks",
            "staff": {"eyebrow": "What to serve and when"},
            "widgets": [
                {
                    "type": "drinks",
                    "audience": "guest",
                    "groups": [
                        {"title": "Soft drinks", "layout": "inline", "items": ["water", "juice"]},
                        {"title": "Wines", "layout": "list", "items": ["fizz", "white", "red"]},
                    ],
                    "note": "Cocktails on request",
                },
                {
                    "type": "drinks",
                    "id": "staff-list",
                    "audience": "staff",
                    "groups": [{"layout": "list", "items": ["fizz", "white", "red", "water", "juice"]}],
                    "staff": {"note": "The bar mixes cocktails on request."},
                },
            ],
        },
        {
            "id": "signature",
            "title": "Enjoy the evening!",
            "audience": "guest",
            "widgets": [{"type": "text", "variant": "signature", "text": COUPLE_NAMES}],
        },
    ],
}

_RESERVED19_GUESTS = [
    {
        "token": "egret-5kd2",
        "name": "Greta",
        "seats": [{"number": 19}, {"number": 1, "plusOne": True, "name": "Hugo"}],
    },
    {
        "token": "plover-8mw3",
        "name": "Peggy and Victor",
        "seats": [{"number": 2, "name": "Peggy"}, {"number": 3, "name": "Victor", "requirements": ["vegan"]}],
    },
    {"token": "crane-7m2p", "name": "Boris", "seats": [{"number": 4, "requirements": ["nuts"]}]},
    {"token": "finch-9ad4", "name": "Galina", "seats": [{"number": 5}]},
    {"token": "heron-4tx9", "name": "Olga", "seats": [{"number": 8}, {"number": 9, "plusOne": True}]},
    {"token": "swift-8np2", "name": "Egor", "seats": [{"number": 10, "requirements": ["gluten", "lactose"]}]},
    {"token": "lark-3vk8", "name": "Alyona", "seats": [{"number": 11, "requirements": ["alcohol"]}]},
    {
        "token": "kite-4mz7",
        "name": "Timur",
        "seats": [{"number": 12}],
        "sections": {"signature": {"note": "Thank you for coming all the way from the coast!"}},
    },
    {"token": "owl-6rb9", "name": "Marta", "seats": [{"number": 14, "requirements": ["lactose"]}]},
    {
        "token": "stork-3jw5",
        "name": "Nina",
        "seats": [{"number": 15}, {"number": 16, "plusOne": True, "name": "Oscar"}],
    },
    {
        "token": "robin-2hx6",
        "name": "Gleb",
        "seats": [{"number": 17}],
        "sections": {"main": {"widgets": {"allergy-card": {"visible": False}}}},
    },
    {"token": "wren-5tc3", "name": "Zhanna", "seats": [{"number": 18, "requirements": ["vegan"]}]},
    {"token": "Rk4vTz8QwM2nLp6XhB9cJs", "staff": True},
]


def reserved19() -> tuple[dict, list]:
    """An L-shaped table of 19 seats, seat 13 reserved."""
    return copy.deepcopy(_RESERVED19_MENU), copy.deepcopy(_RESERVED19_GUESTS)


# --------------------------------------------------------------------------
# plain
# --------------------------------------------------------------------------

_PLAIN_MENU = {
    "schemaVersion": 1,
    "coupleNames": COUPLE_NAMES,
    "event": EVENT,
    "staff": {"updated": "1 June 2030", "contact": "Selma (event planner), phone on the event sheet"},
    "dishes": {
        "bread": {"name": "Bread and butter", "ingredients": "Sourdough, salted butter"},
        "salad": {"name": "Garden salad", "ingredients": "Leaves, radish, mustard dressing"},
        "chicken": {"name": "Roast chicken", "ingredients": "Chicken, potatoes, thyme"},
        "cod": {"name": "Baked cod", "ingredients": "Cod, fennel, lemon"},
        "risotto": {"name": "Mushroom risotto", "ingredients": "Rice, mushrooms, parmesan"},
        "tart": {"name": "Apple tart", "ingredients": "Apples, pastry, cream"},
    },
    "sets": {
        "meat": {"title": "Set 1", "hint": "Meat", "courses": ["chicken", "tart"]},
        "fish": {"title": "Set 2", "hint": "Fish", "courses": ["cod", "tart"]},
        "veggie": {"title": "Set 3", "hint": "Vegetarian", "courses": ["risotto", "tart"]},
    },
    "drinks": {
        "categories": {"soft": {"label": "Soft"}},
        "items": {
            "water": {"category": "soft", "name": "Still and sparkling water"},
            "lemonade": {
                "category": "soft",
                "name": "Homemade lemonade",
                "staff": {"serving": "jugs on the table from 19:00"},
            },
        },
    },
    "sections": [
        {"id": "cover", "type": "cover"},
        {"id": "seats", "widgets": [{"type": "seating"}]},
        {"id": "starters", "title": "To start", "widgets": [{"type": "dishes", "items": ["bread", "salad"]}]},
        {
            "id": "main",
            "title": "Main course",
            "eyebrow": "Choose one of three sets",
            "widgets": [{"type": "sets", "items": ["meat", "fish", "veggie"]}],
        },
        {
            "id": "drinks",
            "title": "Drinks",
            "widgets": [
                {
                    "type": "drinks",
                    "groups": [{"layout": "inline", "items": ["water", "lemonade"]}],
                    "staff": {"note": "Refill the jugs from the bar."},
                }
            ],
        },
        {
            "id": "signature",
            "title": "Enjoy the evening!",
            "audience": "guest",
            "widgets": [{"type": "text", "variant": "signature", "text": COUPLE_NAMES}],
        },
    ],
}

_PLAIN_GUESTS = [
    {"token": "lynx-5qd8", "name": "Lev", "seats": [{"number": 1}]},
    {"token": "otter-2hm7", "name": "Klara", "seats": [{"number": 2}, {"number": 3, "plusOne": True}]},
    {"token": "badger-8wt4", "name": "Rita", "seats": [{"number": 4}]},
    {"token": "Zw3Lq8Vn5Tx2Pk7Wm4Hc9e", "staff": True},
]


def plain() -> tuple[dict, list]:
    """No table, no dietary notes: four seats taken."""
    return copy.deepcopy(_PLAIN_MENU), copy.deepcopy(_PLAIN_GUESTS)


# --------------------------------------------------------------------------
# parts
# --------------------------------------------------------------------------

#: The texts of the section after the drinks: (heading, text, audience).
INFO = (
    ("Smoking", "Smoking is fine on the terrace by the river.", "all"),
    ("Instant camera", "An instant camera waits at the bar: take a picture and leave it for the couple.", "all"),
    ("Clearing up", "Bring the camera back to the bar at the end of the evening.", "staff"),
)


def parts() -> tuple[dict, list]:
    """`reserved19` with a section of parts for the food and one of texts."""
    menu, guests = reserved19()
    sections = menu["sections"]
    starters, main = sections[2], sections[3]
    food = {
        "id": "food",
        "title": "Food",
        "nav": "Food",
        "widgets": [
            {"type": "heading", "title": "Starters", "eyebrow": starters["eyebrow"], "staff": starters["staff"]},
            *starters["widgets"],
            {"type": "heading", "title": "Main course", "eyebrow": main["eyebrow"], "staff": main["staff"]},
            *main["widgets"],
        ],
    }
    info = {"id": "info", "title": "Good to know", "nav": "Info", "widgets": []}
    for title, text, audience in INFO:
        extra = {} if audience == "all" else {"audience": audience}
        info["widgets"] += [{"type": "heading", "title": title, **extra}, {"type": "text", "text": text, **extra}]
    sections[2:4] = [food]
    sections.insert(len(sections) - 1, info)
    sections[1]["nav"] = "Seats"
    sections[3]["nav"] = "Drinks"
    for record in guests:
        overrides = record.get("sections") or {}
        if "main" in overrides:
            overrides["food"] = overrides.pop("main")
    return menu, guests


# --------------------------------------------------------------------------
# serbian
# --------------------------------------------------------------------------

#: Every word of the pages in Serbian (Latin script).
SERBIAN_STRINGS = {
    "pageTitle": "Jelovnik večere",
    "staffVersion": "Verzija za osoblje · ne za goste",
    "updated": "ažurirano {date}",
    "contact": "Kontakt tokom večeri: {contact}",
    "sections": "Odeljci",
    "tablePlan": "Raspored stola: {table}, {seats}. {yours}: {colours}",
    "seatCount": {"one": "{n} mesto", "few": "{n} mesta", "other": "{n} mesta"},
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
    "guestCount": {"one": "{n} gost", "few": "{n} gosta", "other": "{n} gostiju"},
    "noteCount": {"one": "{n} napomena o ishrani", "few": "{n} napomene o ishrani", "other": "{n} napomena o ishrani"},
}

SERBIAN_COUPLE_NAMES = "Ivan i Vesna"

_SERBIAN_MENU = {
    "schemaVersion": 1,
    "lang": "sr-Latn",
    "strings": SERBIAN_STRINGS,
    "coupleNames": SERBIAN_COUPLE_NAMES,
    "event": {"title": "Večera za godišnjicu", "when": "15. jun 2030, 19:00", "place": "Bistro Obala · Ulica primera 5"},
    "staff": {
        "updated": "12. jun 2030",
        "contact": "Selma (organizatorka) · +00 000 000 00 00",
        "reminder": "Link samo za osoblje — molimo ne pokazujte ovu stranicu gostima.",
    },
    "requirements": {
        "nuts": {"letter": "O", "label": "bez orašastih plodova", "avoids": ["nuts"]},
        "gluten": {"letter": "G", "label": "bez glutena", "avoids": ["gluten"]},
        "lactose": {"letter": "L", "label": "bez laktoze", "avoids": ["lactose"]},
        "vegan": {"letter": "Ž", "label": "bez životinjskih namirnica"},
        "alcohol": {"letter": "Č", "label": "čaša bez alkohola"},
    },
    "allergens": {
        "nuts": {"label": "orašasti plodovi"},
        "gluten": {"label": "gluten"},
        "lactose": {"label": "laktoza"},
    },
    "couple": {
        "label": "Ivan · Vesna",
        "members": [
            {"seat": 6, "name": "Vesna", "role": "domaćica"},
            {"seat": 7, "name": "Ivan", "role": "domaćin", "requirements": ["gluten"]},
        ],
    },
    "reservedSeats": [13],
    "table": {**l_table_19(), "label": "Sto u obliku slova L"},
    "dishes": {
        "bruschetta": {
            "name": "Brusketi s paradajzom",
            "ingredients": "Kiselo testo, paradajz, bosiljak",
            "staff": {"allergens": ["gluten"], "swaps": {"gluten": "poslužiti paradajz na kriškama krastavca"}},
        },
        "cheese-board": {
            "name": "Daska sireva",
            "ingredients": "Tri vrste sira, med, orasi",
            "staff": {
                "allergens": ["lactose", "nuts"],
                "swaps": {
                    "lactose": "umesto toga doneti voćni tanjir",
                    "nuts": "poslužiti porciju bez oraha na posebnom tanjiru",
                },
            },
        },
        "hummus": {
            "name": "Humus s povrćem",
            "ingredients": "Leblebije, tahini, šargarepa, krastavac",
            "staff": {"allergens": [], "tags": ["vegansko", "bez glutena"]},
        },
        "melon": {
            "name": "Dinja s mentom",
            "ingredients": "Dinja, menta, limeta",
            "staff": {"allergens": [], "note": "Samo kada gost traži nešto drugo"},
        },
        "salmon": {
            "name": "Marinirani losos",
            "ingredients": "Losos, mirođija, kisela pavlaka",
            "staff": {"allergens": ["lactose"], "swaps": {"lactose": "poslužiti prvo jelo bez kisele pavlake"}},
        },
        "cod": {
            "name": "Pečeni bakalar u korici od badema",
            "ingredients": "Bakalar, bademi, spanać",
            "staff": {"allergens": ["nuts"], "swaps": {"nuts": "poslužiti drugo jelo bez korice"}},
        },
        "carpaccio": {
            "name": "Goveđi karpačo",
            "ingredients": "Govedina, rukola, krutoni",
            "staff": {"allergens": ["gluten"], "swaps": {"gluten": "poslužiti prvo jelo bez krutona"}},
        },
        "duck": {
            "name": "Pačetina s korenastim povrćem",
            "ingredients": "Pačetina, šargarepa, paškanat, sos",
            "staff": {"allergens": [], "swaps": {"vegan": "umesto toga poslužiti pečeno korenasto povrće sa sočivom"}},
        },
    },
    "sets": {
        "fish": {"title": "Meni A", "hint": "Riba", "eyebrow": "dva jela", "courses": ["salmon", "cod"],
                 "pairing": "belo vino"},
        "meat": {"title": "Meni B", "hint": "Meso", "eyebrow": "dva jela", "courses": ["carpaccio", "duck"],
                 "pairing": "crno vino"},
    },
    "drinks": {
        "categories": {
            "sparkling": {"label": "Penušavo"},
            "white": {"label": "Belo"},
            "red": {"label": "Crno"},
            "soft": {"label": "Bezalkoholno"},
        },
        "items": {
            "fizz": {
                "category": "sparkling",
                "name": "Primer Brut, Podrumi Obala",
                "details": "Dolina Primer · Šardone",
                "servedWith": "uz predjela",
                "staff": {"bottles": "6 boca", "serving": "dobro rashlađeno", "swaps": {"alcohol": "bezalkoholno penušavo"}},
            },
            "white": {
                "category": "white",
                "name": "Primer belo, Imanje Brdo",
                "details": "Primorje Primer · Sovinjon blan",
                "servedWith": "uz meni A",
                "staff": {"bottles": "4 boce"},
            },
            "red": {
                "category": "red",
                "name": "Primer crno, Vinarija Stari mlin",
                "details": "Brda Primer · Pino noar",
                "servedWith": "uz meni B",
                "staff": {"bottles": "4 boce", "serving": "otvoriti do 18:30"},
            },
            "water": {"category": "soft", "name": "Negazirana i gazirana voda"},
            "juice": {
                "category": "soft",
                "name": "Limunada i sok od jabuke",
                "staff": {"serving": "bokali na stolu od 19:00"},
            },
        },
    },
    "sections": [
        {"id": "cover", "type": "cover"},
        {
            "id": "seats",
            "widgets": [
                {"type": "seating", "staff": {"footnote": "Mesto 13 ostaje slobodno celo veče: ostavite pribor na njemu."}}
            ],
        },
        {
            "id": "starters",
            "title": "Predjela",
            "eyebrow": "Za ceo sto",
            "staff": {"eyebrow": "Za ceo sto · na stolu do 19:15"},
            "widgets": [
                {"type": "dishes", "items": ["bruschetta", "cheese-board", "hummus"]},
                {"type": "dishes", "audience": "staff", "title": "Na zahtev", "items": ["melon"]},
            ],
        },
        {
            "id": "main",
            "title": "Glavno jelo",
            "eyebrow": "Izaberite jedan od dva menija",
            "staff": {"eyebrow": "Dva menija · gosti biraju za stolom"},
            "widgets": [
                {
                    "type": "sets",
                    "items": ["fish", "meat"],
                    "note": "Konobar će uzeti vašu porudžbinu posle predjela.",
                    "staff": {"note": "Porudžbine uzmite kad predjela budu na stolu."},
                },
                {
                    "type": "text",
                    "id": "allergy-card",
                    "audience": "guest",
                    "variant": "card",
                    "text": "Nešto ne jedete? Recite konobaru: kuhinja će prilagoditi jela.",
                },
            ],
        },
        {
            "id": "drinks",
            "title": "Pića",
            "staff": {"eyebrow": "Šta služiti i kada"},
            "widgets": [
                {
                    "type": "drinks",
                    "audience": "guest",
                    "groups": [
                        {"title": "Bezalkoholna pića", "layout": "inline", "items": ["water", "juice"]},
                        {"title": "Vina", "layout": "list", "items": ["fizz", "white", "red"]},
                    ],
                    "note": "Kokteli na zahtev",
                },
                {
                    "type": "drinks",
                    "id": "staff-list",
                    "audience": "staff",
                    "groups": [{"layout": "list", "items": ["fizz", "white", "red", "water", "juice"]}],
                    "staff": {"note": "Bar priprema koktele na zahtev."},
                },
            ],
        },
        {
            "id": "signature",
            "title": "Uživajte u večeri!",
            "audience": "guest",
            "widgets": [{"type": "text", "variant": "signature", "text": SERBIAN_COUPLE_NAMES}],
        },
    ],
}

_SERBIAN_GUESTS = [
    {"token": "galeb-5kd2", "name": "Jelena", "seats": [{"number": 19}, {"number": 1, "plusOne": True, "name": "Đorđe"}]},
    {
        "token": "vrabac-8mw3",
        "name": "Ana i Miloš",
        "seats": [{"number": 2, "name": "Ana"}, {"number": 3, "name": "Miloš", "requirements": ["vegan"]}],
    },
    {"token": "roda-7m2p", "name": "Bojan", "seats": [{"number": 4, "requirements": ["nuts"]}]},
    {"token": "sova-9ad4", "name": "Gordana", "seats": [{"number": 5}]},
    {"token": "caplja-4tx9", "name": "Olivera", "seats": [{"number": 8}, {"number": 9, "plusOne": True}]},
    {"token": "senica-8np2", "name": "Željko", "seats": [{"number": 10, "requirements": ["gluten", "lactose"]}]},
    {"token": "seva-3vk8", "name": "Aleksandra", "seats": [{"number": 11, "requirements": ["alcohol"]}]},
    {
        "token": "kos-4mz7",
        "name": "Tihomir",
        "seats": [{"number": 12}],
        "sections": {"signature": {"note": "Hvala što ste došli čak sa obale!"}},
    },
    {"token": "zeba-6rb9", "name": "Marija", "seats": [{"number": 14, "requirements": ["lactose"]}]},
    {"token": "lasta-3jw5", "name": "Nađa", "seats": [{"number": 15}, {"number": 16, "plusOne": True, "name": "Ognjen"}]},
    {
        "token": "detlic-2hx6",
        "name": "Goran",
        "seats": [{"number": 17}],
        "sections": {"main": {"widgets": {"allergy-card": {"visible": False}}}},
    },
    {"token": "carlija-5tc3", "name": "Žana", "seats": [{"number": 18, "requirements": ["vegan"]}]},
    {"token": "Vm7kQz2RtX9pLb4WnC6sYd", "staff": True},
]


def serbian() -> tuple[dict, list]:
    """`reserved19` in Serbian Latin: 19 seats, seat 13 reserved."""
    return copy.deepcopy(_SERBIAN_MENU), copy.deepcopy(_SERBIAN_GUESTS)


#: Every set by name.
SETS = {"mockup16": mockup16, "reserved19": reserved19, "plain": plain, "parts": parts, "serbian": serbian}

#: The names of the records for two: the seats have names of their own, and
#: the staff page shows those.
RECORDS_FOR_TWO = ("Peggy and Victor", "Ana i Miloš")


def names(guests: list, menu: dict | None = None) -> set[str]:
    """Every name at the table: the records, their seats and the couple."""
    found = set()
    for record in guests:
        if isinstance(record.get("name"), str):
            found.add(record["name"])
        for seat in record.get("seats", []):
            if isinstance(seat.get("name"), str):
                found.add(seat["name"])
    for member in ((menu or {}).get("couple") or {}).get("members", []):
        if isinstance(member.get("name"), str):
            found.add(member["name"])
    return found


def tokens(guests: list) -> set[str]:
    """Every record's token, the staff record included."""
    return {record["token"] for record in guests if isinstance(record.get("token"), str)}


def write_data(directory: Path, menu, guests) -> Path:
    """Write `menu.json` and `guests.json` into `directory` (created)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in (("menu.json", menu), ("guests.json", guests)):
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        (directory / name).write_text(text, encoding="utf-8")
    return directory
