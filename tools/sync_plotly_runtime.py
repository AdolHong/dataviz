from __future__ import annotations

import argparse
import base64
import hashlib
import io
from pathlib import Path
import tarfile
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.0.0"
URL = (
    "https://registry.npmjs.org/plotly.js-dist-min/-/"
    f"plotly.js-dist-min-{VERSION}.tgz"
)
EXPECTED_SHA512 = (
    "Dm6Sr5aHaxDZ7HN6eLRBotMZ9zRYEd+eoimm27B8d2XOFiNpv0oO7QIE0WFwFAfPN16JHM/"
    "6do6kDbasB+ftbQ=="
)
DESTINATION = ROOT / "src" / "dataviz" / "vendor" / "plotly"
ASSETS = {
    "package/plotly.min.js": DESTINATION / f"plotly-{VERSION}.min.js",
    "package/LICENSE": DESTINATION / "LICENSE",
}


def download() -> bytes:
    with urlopen(URL, timeout=60) as response:  # noqa: S310 - fixed HTTPS release URL
        payload = response.read()
    actual = base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
    if actual != EXPECTED_SHA512:
        raise RuntimeError(f"Plotly.js archive integrity mismatch: {actual}")
    return payload


def extract(payload: bytes) -> dict[Path, bytes]:
    extracted: dict[Path, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        for source, destination in ASSETS.items():
            member = members.get(source)
            if member is None or not member.isfile():
                raise RuntimeError(f"Plotly.js archive is missing {source}")
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError(f"Plotly.js archive cannot read {source}")
            extracted[destination] = stream.read()
    banner = extracted[ASSETS["package/plotly.min.js"]][:80]
    if f"plotly.js v{VERSION}".encode() not in banner:
        raise RuntimeError("Plotly.js bundle banner does not match the pinned version")
    return extracted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync the pinned Plotly.js browser Runtime from its npm release."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the vendored assets instead of writing them.",
    )
    args = parser.parse_args()
    extracted = extract(download())
    if args.check:
        stale = [
            path.relative_to(ROOT).as_posix()
            for path, content in extracted.items()
            if not path.is_file() or path.read_bytes() != content
        ]
        if stale:
            raise RuntimeError(f"Plotly.js vendored assets are stale: {', '.join(stale)}")
        print(f"Plotly.js {VERSION} vendored assets are current")
        return 0
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for path, content in extracted.items():
        path.write_bytes(content)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
