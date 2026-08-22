from __future__ import annotations

import re
import unicodedata
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path

from dataviz.errors import WorkspaceError


SEPARATOR = "##"
TRASH_SEGMENT = "__TRASH__"
FOLDER_ID_PREFIX = "folder:"
DASHBOARD_TRASH_PREFIX = "dashboard:"
FOLDER_TRASH_PREFIX = "folder-trash:"

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{value}" for value in range(1, 10)),
    *(f"LPT{value}" for value in range(1, 10)),
}
_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class DashboardLocation:
    segments: tuple[str, ...]
    trashed: bool = False

    @property
    def folder_segments(self) -> tuple[str, ...]:
        return self.segments[:-1]

    @property
    def leaf(self) -> str:
        return self.segments[-1]

    @property
    def logical_path(self) -> str:
        return "/".join(self.segments)

    @property
    def directory_name(self) -> str:
        return encode_dashboard_name(self.segments, trashed=self.trashed)


def normalize_segment(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def validate_segment(value: str) -> str:
    segment = normalize_segment(value)
    if not segment:
        raise WorkspaceError("Folder name cannot be empty")
    if SEPARATOR in segment:
        raise WorkspaceError(f"Folder name cannot contain the logical separator: {SEPARATOR}")
    if segment.casefold() == TRASH_SEGMENT.casefold():
        raise WorkspaceError(f"Folder name is reserved: {TRASH_SEGMENT}")
    if _WINDOWS_INVALID.search(segment):
        raise WorkspaceError('Folder name contains characters unsupported on Windows: <>:"/\\|?*')
    if segment.endswith((" ", ".")):
        raise WorkspaceError("Folder name cannot end with a space or period")
    if segment.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        raise WorkspaceError(f"Folder name is reserved on Windows: {segment}")
    if len(segment) > 80:
        raise WorkspaceError("Folder name cannot exceed 80 characters")
    return segment


def normalize_logical_path(value: str) -> tuple[str, ...]:
    raw = unicodedata.normalize("NFC", value).replace("\\", "/")
    segments = tuple(validate_segment(part) for part in raw.split("/") if part.strip())
    if not segments:
        raise WorkspaceError("Logical folder path cannot be empty")
    return segments


def decode_dashboard_name(name: str) -> DashboardLocation:
    parts = tuple(unicodedata.normalize("NFC", name).split(SEPARATOR))
    trashed = bool(parts and parts[0] == TRASH_SEGMENT)
    segments = parts[1:] if trashed else parts
    if not segments or any(not part for part in segments):
        raise WorkspaceError(f"Invalid encoded dashboard directory name: {name}")
    for segment in segments:
        validate_segment(segment)
    return DashboardLocation(tuple(segments), trashed=trashed)


def decode_dashboard_path(dashboards_root: Path, dashboard_root: Path) -> DashboardLocation:
    relative = dashboard_root.relative_to(dashboards_root)
    parts: list[str] = []
    trashed = False
    for index, physical in enumerate(relative.parts):
        decoded = decode_dashboard_name(physical)
        if decoded.trashed:
            if index != 0 or trashed:
                raise WorkspaceError(f"Trash marker must be the first logical segment: {relative}")
            trashed = True
        parts.extend(decoded.segments)
    return DashboardLocation(tuple(parts), trashed=trashed)


def encode_dashboard_name(segments: tuple[str, ...] | list[str], *, trashed: bool = False) -> str:
    validated = [validate_segment(value) for value in segments]
    parts = ([TRASH_SEGMENT] if trashed else []) + validated
    encoded = SEPARATOR.join(parts)
    if len(encoded) > 220:
        raise WorkspaceError("Encoded dashboard directory name cannot exceed 220 characters")
    return encoded


def folder_id(segments: tuple[str, ...] | list[str]) -> str:
    return FOLDER_ID_PREFIX + _opaque_encode("/".join(validate_segment(part) for part in segments))


def folder_segments(identifier: str) -> tuple[str, ...]:
    if not identifier.startswith(FOLDER_ID_PREFIX):
        raise WorkspaceError(f"Unknown folder id: {identifier}")
    encoded = identifier[len(FOLDER_ID_PREFIX):]
    try:
        return normalize_logical_path(_opaque_decode(encoded))
    except WorkspaceError:
        # Compatibility with the short-lived readable ``folder:a##b`` ids.
        return normalize_logical_path(encoded.replace(SEPARATOR, "/"))


def dashboard_trash_id(directory_name: str) -> str:
    return DASHBOARD_TRASH_PREFIX + _opaque_encode(directory_name)


def dashboard_trash_name(identifier: str) -> str:
    if not identifier.startswith(DASHBOARD_TRASH_PREFIX):
        raise WorkspaceError(f"Unknown dashboard trash id: {identifier}")
    encoded = identifier[len(DASHBOARD_TRASH_PREFIX):]
    try:
        return _opaque_decode(encoded)
    except WorkspaceError:
        return encoded


def folder_trash_id(segments: tuple[str, ...] | list[str]) -> str:
    return FOLDER_TRASH_PREFIX + _opaque_encode(
        "/".join(validate_segment(part) for part in segments)
    )


def folder_trash_segments(identifier: str) -> tuple[str, ...]:
    if not identifier.startswith(FOLDER_TRASH_PREFIX):
        raise WorkspaceError(f"Unknown folder trash id: {identifier}")
    encoded = identifier[len(FOLDER_TRASH_PREFIX):]
    try:
        return normalize_logical_path(_opaque_decode(encoded))
    except WorkspaceError:
        return normalize_logical_path(encoded.replace(SEPARATOR, "/"))


def _opaque_encode(value: str) -> str:
    return urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _opaque_decode(value: str) -> str:
    try:
        padding = "=" * (-len(value) % 4)
        return urlsafe_b64decode(value + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise WorkspaceError("Invalid navigation identifier") from error
