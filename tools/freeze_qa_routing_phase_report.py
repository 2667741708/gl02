"""Freeze reviewed phase evidence without raw answers, messages, identities or measurements."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
COMMITS = {"v10":"6d2a47aeb16e24cf71e228c0c355b4931b6c6a27", "v11":"9c52d69e2d027bc1dccc42cfd94c65254ee6e803", "v12":"7220e6867c62fb161d2333057fcf130a3dfabb0d"}
TESTS = {"v10":79,"v11":88,"v12":137}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=COMMITS, required=True)
    args = parser.parse_args()
    version = args.version
    release = ROOT / f".codex_runtime/qa-routing-{version}/release"
    round_id = f"retest-routing-{version}-20260916-" + ("r2" if version == "v10" else "r1")
    directory = ROOT / ".codex_runtime/qa-live" / round_id
    progress = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
    if progress["state"] != "completed": raise ValueError("Only a determinate completed collection may be frozen")
    activation = json.loads((release / "frozen-activation.json").read_text(encoding="utf-8"))
    results = []
    for path in sorted(directory.glob("TPL-*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        final = row.get("final") or {}
        failed = version == "v12" and row["case_id"] in ("TPL-V12-KB-LIVE", "TPL-V12-UNKNOWN-LIVE")
        reasons = ["document original subtask passed; live pressure missing unit and includes unrequested metrics"] if failed else []
        results.append({"case_id":row["case_id"],"state":"answer_contract_failed" if failed else "passed",
                        "review_reasons":reasons, "request_count":row["request_count"],
                        "sse_done":bool(row.get("terminated")), "answer_chars":len(row.get("answer") or ""),
                        "answer_sha256":hashlib.sha256((row.get("answer") or "").encode("utf-8")).hexdigest(),
                        "route":final.get("answer_route"), "terminal_state":final.get("completion",{}).get("terminal_state"),
                        "messages_projection":final.get("messages_projection"),"message_count":len(final.get("messages") or []),
                        "tool_start_count":len(row.get("tool_starts") or []),"model_request_count":final.get("model_request_count")})
    payload = {"schema":"bf.qa.routing-production-review.v1", "requirement_id":"REQ-QA-FULL-ISSUE-INVENTORY-20260916",
               "checked_at":"2026-09-16", "version":version, "production_commit":COMMITS[version],
               "focused_tests_passed":TESTS[version], "round":round_id, "requests":progress["requests"],
               "automatic_post_retries":progress["automatic_retries"], "counts":{"passed":sum(r["state"]=="passed" for r in results),"failed":sum(r["state"]=="answer_contract_failed" for r in results)},
               "deployment":activation, "review_method":"Original-text and expected behavior inspected; V12 independently reviewed after release. Nonempty and SSE done alone are not passing signals.",
               "results":results, "privacy":"No raw answers, conversation payloads, production measurements or identities."}
    output = ROOT / f"tests/qa_regression/routing_{version}_production_review_20260916.json"
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"version":version,"requests":payload["requests"],"counts":payload["counts"]}))

if __name__ == "__main__": main()
