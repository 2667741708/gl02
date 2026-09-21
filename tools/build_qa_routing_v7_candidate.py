"""Prepare the single-file V7 history SQL compatibility repair from accepted V6."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v6-candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = args.v6_candidate.resolve()
    expected = '2fecd6d60ca4ad3c91674a63ff2193bb76c592076069f90967c5c31d22f3d9be'
    if hashlib.sha256((baseline / 'qa_history_projection.py').read_bytes()).hexdigest() != expected:
        raise ValueError('Accepted V6 history baseline mismatch')
    args.output.mkdir(parents=True, exist_ok=True)
    for path in baseline.glob('*.py'):
        shutil.copyfile(path, args.output / path.name)
    source = Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend/qa_history_projection.py'
    shutil.copyfile(source, args.output / source.name)
    result = {'ok': True, 'schema': 'bf.qa.routing-v7-build.v1', 'baseline_commit': 'dd34e235f75d9f474923c4094c47e035e8328229', 'write_set': [source.name], 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    (args.output / 'build.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
