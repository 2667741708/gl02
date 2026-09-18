"""Build a private provenance fixture from completed once-only test results."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', type=Path, action='append', required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / '.codex_runtime').resolve()) or output.exists():
        raise ValueError('fixture must be new and private')
    results = {}
    for directory in args.round:
        for path in directory.glob('TPL-*.json'):
            row = json.loads(path.read_text(encoding='utf-8'))
            case_id = row['case_id']
            final = row.get('final') or {}
            if (case_id in results or row.get('determinate') is not True
                    or row.get('terminated') is not True or final.get('ok') is not True
                    or row.get('request_count') != 1 or not path.with_suffix('.claim').exists()):
                raise ValueError('result is duplicated, incomplete or unclaimed')
            users = [message for message in final.get('messages', []) if message.get('role') == 'user']
            if len(users) != 1 or users[0]['content'] != row['question']:
                raise ValueError('current turn projection required')
            results[case_id] = {'case_id':case_id,'user_message_id':users[0]['id'],
                'conversation_id':final['conversation']['id'],
                'question_sha256':hashlib.sha256(row['question'].encode('utf-8')).hexdigest()}
    spec = json.loads(args.spec.read_text(encoding='utf-8'))
    if len({row['case_id'] for row in spec}) != len(spec) or set(results) != {row['case_id'] for row in spec}:
        raise ValueError('fixture must account for every completed test turn')
    fixture = [{**results[row['case_id']], 'objects':row['objects'], 'window':row.get('window')} for row in spec]
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'known_test_turns':len(fixture),'private_fixture':True}))


if __name__ == '__main__': main()
