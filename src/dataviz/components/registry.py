from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml


COMPONENT_PACKAGE_SCHEMA = "dataviz/component-package/v1"
COMPONENT_STORY_SCHEMA = "dataviz/component-story/v1"
COMPONENT_TEST_SCHEMA = "dataviz/component-test/v1"
COMPONENT_PACKAGE_REPORT_SCHEMA = "dataviz/component-package-report/v3"
PACKAGE_ROOT = Path(__file__).resolve().parent / "packages"
DATAVIZ_ROOT = PACKAGE_ROOT.parent.parent
REQUIRED_FILES = (
    "manifest.yaml",
    "controller.js",
    "adapter.js",
    "style.css",
    "story.yaml",
    "test.yaml",
)


class ComponentPackageError(RuntimeError):
    """Raised when packaged component metadata is internally inconsistent."""


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - parser includes useful detail
        raise ComponentPackageError(f"Cannot read Component Package metadata: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ComponentPackageError(f"Component Package document must be a mapping: {path}")
    return value


@dataclass(frozen=True)
class ComponentPackage:
    name: str
    root: Path
    manifest: dict[str, Any]
    story_document: dict[str, Any]
    test_document: dict[str, Any]

    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(str(item["id"]) for item in self.manifest.get("components", []))

    @property
    def dependencies(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.manifest.get("dependencies", []))

    @property
    def stories(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.story_document.get("stories", []))

    @property
    def tests(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.test_document.get("tests", []))

    def asset(self, kind: str) -> Path:
        relative = self.manifest.get("runtime", {}).get(kind)
        if not relative:
            raise ComponentPackageError(f"Package {self.name} has no runtime.{kind} asset")
        path = (self.root / str(relative)).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise ComponentPackageError(f"Package {self.name} has an invalid runtime.{kind} asset: {relative}")
        return path

    def public_metadata(self) -> dict[str, Any]:
        return {
            "schema": self.manifest["schema"],
            "package": self.name,
            "version": self.manifest["version"],
            "category": self.manifest["category"],
            "purpose": self.manifest.get("purpose", ""),
            "dependencies": list(self.dependencies),
            "components": list(self.component_ids),
            "implementation": dict(self.manifest["implementation"]),
            "runtime": {
                key: f"components/packages/{self.name}/{value}"
                for key, value in self.manifest.get("runtime", {}).items()
            },
            "stories": [item["id"] for item in self.stories],
            "tests": [item["id"] for item in self.tests],
        }


def _load_package(root: Path) -> ComponentPackage:
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ComponentPackageError(f"Package {root.name} is missing: {', '.join(missing)}")
    manifest = _read_yaml(root / "manifest.yaml")
    story = _read_yaml(root / "story.yaml")
    tests = _read_yaml(root / "test.yaml")
    if manifest.get("schema") != COMPONENT_PACKAGE_SCHEMA:
        raise ComponentPackageError(f"Package {root.name} must use {COMPONENT_PACKAGE_SCHEMA}")
    if manifest.get("package") != root.name:
        raise ComponentPackageError(
            f"Package directory {root.name} does not match manifest package {manifest.get('package')!r}"
        )
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        raise ComponentPackageError(f"Package {root.name} must declare a version")
    if not isinstance(manifest.get("category"), str) or not manifest["category"].strip():
        raise ComponentPackageError(f"Package {root.name} must declare a category")
    if not isinstance(manifest.get("dependencies", []), list):
        raise ComponentPackageError(f"Package {root.name} dependencies must be a list")
    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict):
        raise ComponentPackageError(f"Package {root.name} must declare implementation")
    mode = implementation.get("mode")
    sources = implementation.get("sources")
    if mode not in {"package", "bridge"}:
        raise ComponentPackageError(
            f"Package {root.name} implementation.mode must be package or bridge"
        )
    if not isinstance(sources, list) or any(
        not isinstance(source, str) or not source for source in sources
    ):
        raise ComponentPackageError(
            f"Package {root.name} implementation.sources must be a list of paths"
        )
    if mode == "package" and sources:
        raise ComponentPackageError(
            f"Package {root.name} owns its implementation and must not declare bridge sources"
        )
    if mode == "bridge" and not sources:
        raise ComponentPackageError(
            f"Bridge Package {root.name} must identify its current implementation sources"
        )
    for source in sources:
        source_path = (DATAVIZ_ROOT / source).resolve()
        if not source_path.is_relative_to(DATAVIZ_ROOT) or not source_path.is_file():
            raise ComponentPackageError(
                f"Package {root.name} has an invalid bridge source: {source}"
            )
    if not isinstance(manifest.get("runtime"), dict):
        raise ComponentPackageError(f"Package {root.name} runtime must be a mapping")
    if story.get("schema") != COMPONENT_STORY_SCHEMA:
        raise ComponentPackageError(f"Package {root.name} story.yaml must use {COMPONENT_STORY_SCHEMA}")
    if tests.get("schema") != COMPONENT_TEST_SCHEMA:
        raise ComponentPackageError(f"Package {root.name} test.yaml must use {COMPONENT_TEST_SCHEMA}")
    if not isinstance(story.get("stories"), list):
        raise ComponentPackageError(f"Package {root.name} story.yaml stories must be a list")
    if not isinstance(tests.get("tests"), list):
        raise ComponentPackageError(f"Package {root.name} test.yaml tests must be a list")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise ComponentPackageError(f"Package {root.name} must own at least one component")
    if manifest.get("category") == "data-entry" and len(components) != 1:
        raise ComponentPackageError(
            f"Data Entry Package {root.name} must own exactly one component"
        )
    for item in components:
        if not isinstance(item, dict) or not item.get("id") or not item.get("purpose"):
            raise ComponentPackageError(f"Package {root.name} has an invalid component declaration")
        if manifest.get("category") == "data-entry":
            if item.get("id") != root.name:
                raise ComponentPackageError(
                    f"Data Entry Package {root.name} must have the same package and component id"
                )
            alignment = item.get("alignment")
            if (
                not isinstance(alignment, dict)
                or alignment.get("design_system") != "Ant Design"
                or not str(alignment.get("official", "")).startswith(
                    "https://ant.design/components/"
                )
                or not isinstance(alignment.get("adopted"), list)
                or not isinstance(alignment.get("omitted"), list)
            ):
                raise ComponentPackageError(
                    f"Data Entry Package {root.name} must declare its Ant Design semantic alignment"
                )
    for item in story["stories"]:
        gallery = item.get("gallery") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or not item.get("id")
            or not item.get("component")
            or not item.get("title")
            or not item.get("summary")
            or not isinstance(gallery, dict)
            or any(not gallery.get(key) for key in ("dashboard", "target", "anchor"))
        ):
            raise ComponentPackageError(f"Package {root.name} has an invalid Story declaration")
    for item in tests["tests"]:
        if (
            not isinstance(item, dict)
            or not item.get("id")
            or not item.get("component")
            or not item.get("kind")
            or not isinstance(item.get("assertions"), list)
            or not item["assertions"]
        ):
            raise ComponentPackageError(f"Package {root.name} has an invalid Test declaration")
    for kind in ("controller", "adapter", "style"):
        relative = manifest.get("runtime", {}).get(kind)
        if relative != f"{kind}.js" and not (kind == "style" and relative == "style.css"):
            raise ComponentPackageError(
                f"Package {root.name} runtime.{kind} must be physically co-located as "
                f"{'style.css' if kind == 'style' else kind + '.js'}"
            )
    package = ComponentPackage(root.name, root, manifest, story, tests)
    for kind in ("controller", "adapter", "style"):
        package.asset(kind)
    return package


@lru_cache(maxsize=1)
def component_packages() -> dict[str, ComponentPackage]:
    if not PACKAGE_ROOT.is_dir():
        raise ComponentPackageError(f"Component Package root is missing: {PACKAGE_ROOT}")
    packages = {
        root.name: _load_package(root)
        for root in sorted(PACKAGE_ROOT.iterdir())
        # Installers can leave empty directory shells while replacing a wheel.
        # A Component Package begins at its manifest; once that exists, all six
        # required files are validated strictly by _load_package.
        if root.is_dir()
        and not root.name.startswith("_")
        and (root / "manifest.yaml").is_file()
    }
    owners: dict[str, str] = {}
    for package in packages.values():
        for component_id in package.component_ids:
            if component_id in owners:
                raise ComponentPackageError(
                    f"Component {component_id} is owned by both {owners[component_id]} and {package.name}"
                )
            owners[component_id] = package.name
        unknown_dependencies = set(package.dependencies) - set(packages)
        if unknown_dependencies:
            raise ComponentPackageError(
                f"Package {package.name} has unknown dependencies: {', '.join(sorted(unknown_dependencies))}"
            )
    return packages


def component_package_for(component_id: str) -> ComponentPackage | None:
    for package in component_packages().values():
        if component_id in package.component_ids:
            return package
    return None


def component_story_catalog() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for package in component_packages().values():
        for story in package.stories:
            story_id = str(story.get("id", ""))
            component_id = str(story.get("component", ""))
            if not story_id or component_id not in package.component_ids:
                raise ComponentPackageError(f"Package {package.name} has an invalid Story: {story!r}")
            if story_id in result:
                raise ComponentPackageError(f"Duplicate Component Story id: {story_id}")
            result[story_id] = {**story, "package": package.name}
    return result


def component_test_catalog() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for package in component_packages().values():
        for case in package.tests:
            test_id = str(case.get("id", ""))
            component_id = str(case.get("component", ""))
            if not test_id or component_id not in package.component_ids:
                raise ComponentPackageError(f"Package {package.name} has an invalid Test: {case!r}")
            if test_id in result:
                raise ComponentPackageError(f"Duplicate Component Test id: {test_id}")
            result[test_id] = {**case, "package": package.name}
    return result


def component_index() -> dict[str, dict[str, Any]]:
    stories_by_component: dict[str, list[dict[str, Any]]] = {}
    tests_by_component: dict[str, list[dict[str, Any]]] = {}
    for story in component_story_catalog().values():
        stories_by_component.setdefault(str(story["component"]), []).append(story)
    for case in component_test_catalog().values():
        tests_by_component.setdefault(str(case["component"]), []).append(case)
    result: dict[str, dict[str, Any]] = {}
    for package in component_packages().values():
        public = package.public_metadata()
        for declaration in package.manifest["components"]:
            component_id = str(declaration["id"])
            result[component_id] = {
                **declaration,
                "package": public,
                "stories": stories_by_component.get(component_id, []),
                "tests": tests_by_component.get(component_id, []),
            }
    return result


def _ordered_packages(component_ids: Iterable[str] | None = None) -> list[ComponentPackage]:
    packages = component_packages()
    wanted = set(packages) if component_ids is None else {
        package.name
        for component_id in component_ids
        if (package := component_package_for(component_id)) is not None
    }
    pending = list(wanted)
    while pending:
        name = pending.pop()
        for dependency in packages[name].dependencies:
            if dependency not in wanted:
                wanted.add(dependency)
                pending.append(dependency)
    ordered: list[ComponentPackage] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ComponentPackageError(f"Component Package dependency cycle at {name}")
        visiting.add(name)
        for dependency in packages[name].dependencies:
            if dependency in wanted:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(packages[name])

    for name in sorted(wanted):
        visit(name)
    return ordered


def component_runtime_assets(component_ids: Iterable[str] | None = None) -> dict[str, Any]:
    packages = _ordered_packages(component_ids)
    return {
        "packages": [package.name for package in packages],
        "style": "\n".join(package.asset("style").read_text(encoding="utf-8") for package in packages),
        "scripts": [
            {
                "package": package.name,
                "kind": kind,
                "source": package.asset(kind).read_text(encoding="utf-8"),
            }
            for package in packages
            for kind in ("controller", "adapter")
        ],
    }


def validate_component_packages(expected_components: Iterable[str] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    try:
        packages = component_packages()
        index = component_index()
        stories = component_story_catalog()
        tests = component_test_catalog()
        _ordered_packages(index)
        missing = sorted(set(expected_components or ()) - set(index))
        if missing:
            errors.append({"code": "missing_component_package", "components": missing})
        components_without_tests = sorted(set(index) - {str(item["component"]) for item in tests.values()})
        if components_without_tests:
            errors.append({"code": "component_without_test", "components": components_without_tests})
    except ComponentPackageError as exc:
        return {
            "schema": COMPONENT_PACKAGE_REPORT_SCHEMA,
            "scope": "package-metadata-and-test-declarations",
            "behavior_tests_executed": False,
            "valid": False,
            "packages": 0,
            "package_implemented": 0,
            "bridge_implemented": 0,
            "components": 0,
            "stories": 0,
            "test_declarations": 0,
            "errors": [{"code": "invalid_component_package", "message": str(exc)}],
        }
    package_implemented = sum(
        package.manifest["implementation"]["mode"] == "package"
        for package in packages.values()
    )
    return {
        "schema": COMPONENT_PACKAGE_REPORT_SCHEMA,
        "scope": "package-metadata-and-test-declarations",
        "behavior_tests_executed": False,
        "valid": not errors,
        "packages": len(packages),
        "package_implemented": package_implemented,
        "bridge_implemented": len(packages) - package_implemented,
        "components": len(index),
        "stories": len(stories),
        "test_declarations": len(tests),
        "errors": errors,
    }
