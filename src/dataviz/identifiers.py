from __future__ import annotations

import re
import hashlib
from typing import Annotated

from pydantic import AfterValidator, StringConstraints


# Machine identifiers are embedded in canonical Output/Selection references,
# URLs, cache keys and Artifact names. Display text belongs in title/label.
STABLE_ID_PATTERN = r"[A-Za-z_](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9_-])?"
_STABLE_ID = re.compile(rf"^{STABLE_ID_PATTERN}$")
_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _portable_stable_id(value: str) -> str:
    if value.split(".", 1)[0].upper() in _WINDOWS_DEVICE_NAMES:
        raise ValueError("id cannot use a reserved Windows device name")
    return value


StableId = Annotated[
    str,
    StringConstraints(pattern=rf"^{STABLE_ID_PATTERN}$"),
    AfterValidator(_portable_stable_id),
]


def is_stable_id(value: str) -> bool:
    return bool(_STABLE_ID.fullmatch(value)) and (
        value.split(".", 1)[0].upper() not in _WINDOWS_DEVICE_NAMES
    )


def fallback_stable_id(value: str, *, prefix: str) -> str:
    """Keep a valid id or derive a deterministic portable fallback."""
    if is_stable_id(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def stable_id_help(kind: str = "id") -> str:
    return (
        f"{kind} must start with an ASCII letter or underscore and contain only "
        "ASCII letters, digits, dot, underscore, or hyphen; it cannot end in a dot "
        "or use a reserved Windows device name (maximum 128 characters)"
    )
