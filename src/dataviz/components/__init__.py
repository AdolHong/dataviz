"""Physical Component Package discovery and runtime asset loading."""

from dataviz.components.registry import (
    COMPONENT_PACKAGE_SCHEMA,
    component_index,
    component_package_for,
    component_packages,
    component_runtime_assets,
    component_story_catalog,
    component_test_catalog,
    validate_component_packages,
)

__all__ = [
    "COMPONENT_PACKAGE_SCHEMA",
    "component_index",
    "component_package_for",
    "component_packages",
    "component_runtime_assets",
    "component_story_catalog",
    "component_test_catalog",
    "validate_component_packages",
]
