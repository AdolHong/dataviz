"""Bind built artifacts to a source revision and explicit CI gate results."""
import argparse
import hashlib
import json
from pathlib import Path


REQUIRED_GATES = {'python-contracts', 'macos-noneditable', 'javascript-syntax', 'browsers'}


def manifest(directory: Path, revision: str, run_url: str, gates: dict) -> dict:
    if not revision or not run_url:
        raise ValueError('source revision and CI run URL are required')
    if set(gates) != REQUIRED_GATES or any(gates[name].get('result') != 'success' for name in REQUIRED_GATES):
        raise ValueError('all required quality jobs must report success')
    artifacts = sorted(path for path in directory.iterdir() if path.is_file() and
                       (path.name.endswith(('.whl', '.tar.gz', '.zip', '.sha256'))))
    if not all(any(path.name.endswith(suffix) for path in artifacts) for suffix in ('.whl', '.tar.gz', '.zip')):
        raise ValueError('wheel, sdist and ZIP must all be present')
    if any(path.is_symlink() for path in artifacts):
        raise ValueError('artifact symlinks are not supported')
    return {'schema': 'dataviz/release-evidence/v1', 'source_revision': revision,
            'ci_run': run_url, 'quality_gates': {name: 'success' for name in sorted(REQUIRED_GATES)},
            'artifacts': [{'name': path.name, 'bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in artifacts]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--run-url', required=True)
    parser.add_argument('--gates', required=True, help='JSON job results from GitHub needs')
    args = parser.parse_args()
    payload = manifest(args.directory, args.revision, args.run_url, json.loads(args.gates))
    (args.directory / 'release-evidence.json').write_text(json.dumps(payload, indent=2) + '\n')


if __name__ == '__main__':
    main()
