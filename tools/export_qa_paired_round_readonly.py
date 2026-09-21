"""Read completed private QA evidence in bounded chunks; never send chat requests."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--offset',type=int,default=0)
    parser.add_argument('--limit',type=int,default=50)
    args=parser.parse_args()
    if args.offset<0 or not 1<=args.limit<=100:raise ValueError('Invalid bounded read')
    progress=json.loads((args.directory/'progress.json').read_text(encoding='utf-8'))
    completed=progress['results']
    rows=[]
    for entry in completed[args.offset:args.offset+args.limit]:
        path=args.directory/(entry['case_id']+'.json')
        content=path.read_bytes()
        row=json.loads(content)
        if row['case_id']!=entry['case_id'] or row['request_count']!=1:
            raise ValueError('Evidence identity or send count mismatch')
        row['result_file_sha256']=hashlib.sha256(content).hexdigest()
        rows.append(row)
    payload={'offset':args.offset,'available':len(completed),'progress':progress,'rows':rows}
    encoded=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    print(json.dumps({'offset':args.offset,'rows':len(rows),'available':len(completed),
        'state':progress['state'],'payload_sha256':hashlib.sha256(encoded).hexdigest(),
        'data_b64':base64.b64encode(zlib.compress(encoded)).decode('ascii')}))


if __name__=='__main__':main()
