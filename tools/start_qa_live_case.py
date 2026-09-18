"""Detach exactly one case collector so an SSH RPC deadline cannot truncate it.

The collector source arrives as base64 and is passed to Python stdin, not saved
as a production module. Exclusive evidence files prevent accidental replay.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--case-json', required=True)
    parser.add_argument('--phase', required=True)
    parser.add_argument('--runner-base64', required=True)
    args = parser.parse_args()
    case = json.loads(args.case_json)
    if not re.fullmatch(r'(?:LIVE-\d{3}|TPL-[A-F0-9]{16})', case['case_id']) or not re.fullmatch(r'(?:before|after)(?:-v\d+)?|templates-v\d+', args.phase):
        raise ValueError('invalid case or phase')
    source = base64.b64decode(args.runner_base64, validate=True)
    compile(source, '<qa-live-collector>', 'exec')
    directory = args.root / 'logs/qa_regression_20260915'
    directory.mkdir(exist_ok=True)
    stem = args.phase + '-' + case['case_id']
    output_path = directory / (stem + '.json')
    error_path = directory / (stem + '.err')
    # Never retry when output exists, even if the earlier transport was lost.
    with output_path.open('xb') as output:
        with error_path.open('xb') as error:
            child = subprocess.Popen(
                [sys.executable, '-X', 'utf8', '-', '--root', str(args.root), '--case-json', args.case_json,
                 '--phase', args.phase, '--execute'],
                stdin=subprocess.PIPE, stdout=output, stderr=error,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            child.stdin.write(source)
            child.stdin.close()
    print(json.dumps({'started': True, 'collector_pid': child.pid, 'case_id': case['case_id'],
                      'output': str(output_path), 'error': str(error_path), 'automatic_replay': False}))


if __name__ == '__main__':
    main()
