"""Stage only the exact locally frozen online test tools and private plan."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    command = [sys.executable, '-X', 'utf8', str(ROOT / 'tools/remote_22012_session.py'), 'run', '--']
    for row in manifest['files']:
        path = Path(row['local']).resolve()
        if not path.is_file() or not path.is_relative_to(ROOT): raise ValueError('Invalid local staging file')
        if not row['remote'].startswith(manifest['stage'] + '/'): raise ValueError('Remote outside exact stage')
        command.extend(['--upload', str(path) + '=' + row['remote']])
    command.extend(['--upload-only', '--workdir', 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW', '--emit-timing-json'])
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__': raise SystemExit(main())
