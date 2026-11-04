"""The names the rest of the package takes from the engine of the build.

The modules of the engine are `_engine` (the template engine, the report of a
command, the checks of the finished output, the output directory, the masking
of tokens, the types of the command line arguments), `_values` (JSON, paths
in messages, ids, tokens), `_checks` (the messages of the data checks),
`_tokens` (the design tokens of a style sheet) and `_icon` (the icon).  The
builder, the checks of the data and the checks of the output use them through
this module only, so `__all__` below is the whole surface they rely on.

Every name is the one it has in its module.  The one alias is
`SCHEMA_MISSING`: `_checks.MISSING`, what the methods of `_Checker` return for
a field without a usable value (`MISSING` is the one of `_engine`, returned by
`read_json`).
"""

from __future__ import annotations

from menu_tools._checks import MISSING as SCHEMA_MISSING
from menu_tools._checks import _Checker
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

#: Everything the package takes from the engine.
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
