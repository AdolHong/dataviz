"""Deprecated compatibility API; use ``dataviz.workspace.selections``."""

from dataviz.workspace.selections import (
    EffectiveSelection,
    SelectionOrigin,
    canonical_selection_key,
    compile_selection_contract,
    resolve_selection_values,
    view_definition,
)

EffectiveFilter = EffectiveSelection
FilterOrigin = SelectionOrigin
canonical_filter_key = canonical_selection_key
compile_filter_contract = compile_selection_contract
resolve_filter_values = resolve_selection_values

__all__ = [
    "EffectiveFilter",
    "FilterOrigin",
    "canonical_filter_key",
    "compile_filter_contract",
    "resolve_filter_values",
    "view_definition",
]
