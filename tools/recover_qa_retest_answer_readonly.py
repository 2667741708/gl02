"""Read a single known lost regression answer; never send or print other messages."""
import argparse
import json
from datetime import datetime
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', required=True)
    parser.add_argument('--after', type=float, required=True)
    parser.add_argument('--before', type=float, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8093/api/qa/bootstrap')
    args = parser.parse_args()
    request = Request(args.url, headers={'Host': '10.30.220.12:8093'}, method='GET')
    with urlopen(request, timeout=15) as response:
        payload = json.load(response)
    rows = payload.get('messages', [])
    matches = []
    for index, row in enumerate(rows):
        if row.get('role') != 'user' or row.get('content') != args.question:
            continue
        try:
            stamp = datetime.fromisoformat(str(row.get('created_at')).replace('Z', '+00:00')).timestamp()
        except (ValueError, TypeError):
            continue
        if not args.after <= stamp <= args.before:
            continue
        answer = next((item for item in rows[index + 1:] if item.get('role') in ('user', 'assistant')), {})
        matches.append({'matched_time': row.get('created_at'), 'answer': answer.get('content', '')[:12000] if answer.get('role') == 'assistant' else '', 'metadata': answer.get('metadata') if answer.get('role') == 'assistant' else None})
    print(json.dumps({'schema': 'bf.qa.single-answer-recovery.v1', 'method': 'GET', 'match_count': len(matches), 'result': matches[0] if len(matches) == 1 else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
