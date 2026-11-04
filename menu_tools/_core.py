"""Shared helpers of the package, re-exported in one place.

The helpers live in `_engine` (templates, command reports, output checks,
the output directory, token masking, command-line argument types),
`_values` (JSON, paths in messages, ids, tokens), `_checks` (messages of the
data checks), `_tokens` (design tokens of a style sheet) and `_icon` (the
icon).  The builder, the data checks and the output checks import them from
this module only, so `__all__` below lists everything they use.

Every name is the one it has in its module, with one alias:
`SCHEMA_MISSING` is `_checks.MISSING`, which the `_Checker` methods return
for a field without a usable value (`MISSING` comes from `_engine` and is
what `read_json` returns).
"""

from __future__ import annotations

from menu_tools._checks import MISSING as SCHEMA_MISSING
from menu_tools._checks import _Checker, _known_list
from menu_tools._engine import (
    CI_ENVIRONMENT_VARIABLES,
    EXIT_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    MAX_REPORTED_PROBLEMS,
    MISSING,
    NAME_MASK,
    BuildError,
    OutputError,
    OutputStats,
    Report,
    Template,
    TemplateError,
    ValidationError,
    _StagedOutput,
    assets_url_path,
    base_path_argument,
    check_html,
    check_out_dir,
    check_output,
    check_rendered,
    check_svg,
    copy_assets,
    display_path,
    load_fragments,
    load_template,
    parse_published_url,
    parse_template,
    read_json,
    running_in_ci,
    strip_html_comments,
    text_to_html,
    token_prefix,
    write_pages,
)
from menu_tools._icon import favicon_svg
from menu_tools._tokens import TokenError, hex_color, load_palette
from menu_tools._values import (
    ID_RULE,
    RESERVED_TOKENS,
    check_token,
    did_you_mean,
    format_size,
    generate_prefixed_token,
    generate_token,
    is_identifier,
    json_type,
    show_id,
)

#: Every name the rest of the package imports from here.
__all__ = [
    # template engine
    "Template",
    "parse_template",
    "check_rendered",
    "load_fragments",
    "load_template",
    "strip_html_comments",
    "text_to_html",
    # errors and the report
    "BuildError",
    "TemplateError",
    "ValidationError",
    "Report",
    "MISSING",
    # data
    "read_json",
    "did_you_mean",
    "is_identifier",
    "show_id",
    "ID_RULE",
    "check_token",
    "generate_token",
    "generate_prefixed_token",
    "RESERVED_TOKENS",
    "json_type",
    "format_size",
    # schema messages
    "_Checker",
    "_known_list",
    "SCHEMA_MISSING",
    # output checks, output directory, masking
    "check_output",
    "check_html",
    "check_svg",
    "assets_url_path",
    "base_path_argument",
    "MAX_REPORTED_PROBLEMS",
    "display_path",
    "NAME_MASK",
    "check_out_dir",
    "copy_assets",
    "write_pages",
    "OutputError",
    "OutputStats",
    "_StagedOutput",
    # design tokens and the icon
    "load_palette",
    "hex_color",
    "TokenError",
    "favicon_svg",
    # command line
    "running_in_ci",
    "CI_ENVIRONMENT_VARIABLES",
    "parse_published_url",
    "token_prefix",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_USAGE",
]
