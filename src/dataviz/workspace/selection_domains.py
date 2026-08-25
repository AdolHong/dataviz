from __future__ import annotations

def selection_option_domain_references(dashboard) -> dict[str, list[str]]:
    """Project immutable option domains from the Dashboard dependency contract."""

    contract = dashboard.dependency_contract
    return {
        key: list(references)
        for key, references in contract.selection_option_domains.items()
    }
