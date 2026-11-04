"""The icon of the pages, derived from the design tokens.

``favicon.svg`` is a small neutral mark (plain geometry).  Its colours come
from the ``:root`` tokens of ``assets/app.css``, so the icon follows the
design: change the tokens and build again.  The build writes it straight into
the output directory; nothing generated is kept in the repository.  The same
input gives a byte-identical file.

Standard library only.
"""

from __future__ import annotations

from menu_tools._tokens import Palette, hex_color


def favicon_svg(palette: Palette) -> bytes:
    """The icon: a rounded accent square with a diamond outline and a dot."""
    accent = hex_color(palette.accent)
    mark = hex_color(palette.on_accent)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="14" fill="{accent}"/>'
        f'<path d="M32 13 51 32 32 51 13 32z" fill="none" stroke="{mark}" '
        'stroke-width="4" stroke-linejoin="round"/>'
        f'<circle cx="32" cy="32" r="5" fill="{mark}"/>'
        "</svg>\n"
    ).encode("utf-8")
