"""Read-only QA evidence extraction; stdout is compressed private JSON, never a replay."""
from __future__ import annotations
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path
import zlib

def extract(root, offset, limit):
    records = []
    batches = []
    for name in ("r1", "r2", "r3"):
        folder = root / ("logs/qa_templates_20260915_v2_" + name)
        p = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        batches.append({k:v for k,v in p.items() if k != "results"})
        for row in p.get("results", []):
            records.append((name, folder, row))
    selected = records[offset:offset + limit]
    rows = []
    for name, folder, row in selected:
        raw = (folder / (row["case_id"] + ".json")).read_bytes()
        d = json.loads(raw)
        item = dict(row)
        item.update(batch=name, result_sha256=hashlib.sha256(raw).hexdigest())
        for key in ("question", "answer", "error_code", "http_status", "done", "terminated",
                    "transport_error", "request_count", "automatic_retries"):
            item[key] = d.get(key)
        item["answer_sha256"] = hashlib.sha256((d.get("answer") or "").encode()).hexdigest()
        item["final"] = {k:v for k,v in (d.get("final") or {}).items()
                         if k in ("ok","answer_route","grounding_status","model_request_count","error","error_code")}
        item["tools"] = []
        for t in d.get("tool_results", []):
            result = t.get("result") or {}
            brief = {k:result.get(k) for k in ("ok","error","error_type","code","message","status")
                     if isinstance(result, dict) and k in result}
            item["tools"].append({k:t.get(k) for k in ("tool","server_id","arguments","elapsed_ms","policy")} | {"result":brief})
        item["tool_starts"] = [{k:t.get(k) for k in ("tool","arguments","round","route")} for t in d.get("tool_starts", [])]
        rows.append(item)
    return {"schema":"bf.qa.private-audit-extract.v1","checked_at":datetime.datetime.now().isoformat(),
            "offset":offset,"limit":limit,"available":len(records),"batches":batches,"rows":rows}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args()
    data=json.dumps(extract(a.root,a.offset,a.limit),ensure_ascii=False).encode("utf-8")
    print(base64.b64encode(zlib.compress(data)).decode("ascii"))

if __name__ == "__main__":
    main()
