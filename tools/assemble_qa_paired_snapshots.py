"""Decode only private bounded read snapshots locally; publish no raw evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    parts=[]
    for path in sorted(args.directory.glob('chunk-*.json')):
        outer=json.loads(path.read_text(encoding='utf-8'))
        raw=zlib.decompress(base64.b64decode(outer['data_b64'],validate=True))
        if hashlib.sha256(raw).hexdigest()!=outer['payload_sha256']:
            raise ValueError('Private snapshot hash mismatch')
        parts.append(json.loads(raw))
    rows=[]
    for part in parts:
        if part['offset']!=len(rows):raise ValueError('Snapshot gap or overlap')
        rows.extend(part['rows'])
    if len({row['case_id'] for row in rows})!=len(rows):raise ValueError('Duplicate results')
    output=args.directory/'results.private.json'
    value={'rows':rows,'progress':parts[-1]['progress'] if parts else None}
    output.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok':True,'rows':len(rows),'available':parts[-1]['available'] if parts else 0}))


if __name__=='__main__':main()
