"""Screen knowledge question/reference consistency without uploading original text."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def parse_cases(text):
    rows = []
    for match in re.finditer(r"^#### (FG-[TA]-\d+) (.+?)\n(.*?)(?=^#### |\Z)", text, re.M | re.S):
        case_id, title, body = match.groups()
        question = re.search(r"^- 测试问题：(.+)$", body, re.M)
        expected = re.search(r"^- 标准答案：(.+)$", body, re.M)
        section = re.search(r"^- 原文章节：`([^`]+)`", body, re.M)
        ref = re.search(r"^- 期望知识块：`([^`]+)`", body, re.M)
        rows.append({"oracle_id": case_id, "title": title.strip(), "question": question.group(1).strip() if question else "", "expected": expected.group(1).strip() if expected else "", "section_code": section.group(1) if section else "", "reference_id": ref.group(1) if ref else ""})
    return rows

def inspect(rows):
    groups = {}
    for row in rows:
        groups.setdefault(re.sub(r"\s+", "", row["question"]), []).append(row)
    out = []
    for row in rows:
        reasons = []
        quoted = re.search(r"“([^”]+)”", row["question"])
        leaf = quoted.group(1).split(">")[ -1].strip() if quoted else ""
        code = re.match(r"(\d+(?:\.\d+)*)", leaf)
        if not all(row[key] for key in ("question", "expected", "section_code", "reference_id")):
            reasons.append("required_oracle_field_missing")
        expected_code = row["section_code"]
        parent_reference = row["oracle_id"].startswith("FG-A-")
        code_consistent = bool(code and (code.group(1) == expected_code or (parent_reference and expected_code.startswith(code.group(1) + "."))))
        if code and re.fullmatch(r"\d+(?:\.\d+)*", expected_code) and not code_consistent:
            reasons.append("question_section_code_conflict")
        duplicates = groups.get(re.sub(r"\s+", "", row["question"]), [])
        if len({(item["expected"], item["section_code"]) for item in duplicates}) > 1:
            reasons.append("same_question_conflicting_expected_answers")
        out.append({"oracle_id": row["oracle_id"], "question_sha256": hashlib.sha256(row["question"].encode()).hexdigest(), "state": "oracle_blocked" if reasons else "consistent_pending_semantic_review", "reasons": reasons, "question_section_code": code.group(1) if code else None, "expected_section_code": row["section_code"]})
    return out

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = ROOT / "PT/三规二制高炉长工长知识库测试题库.md"
    rows = parse_cases(source.read_text(encoding="utf-8"))
    if len(rows) != 833:
        raise ValueError(f"Knowledge denominator changed: {len(rows)}")
    results = inspect(rows)
    payload = {"schema": "bf.qa.knowledge-oracle-audit.v1", "requirement_id": "REQ-QA-FULL-ISSUE-INVENTORY-20260916", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "total": len(rows), "oracle_blocked": sum(row["state"] == "oracle_blocked" for row in results), "semantic_passed": 0, "results": results, "privacy": "Question hashes, identifiers and conflict reasons only; no original text or production answers."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in payload.items() if key != "results"}))

if __name__ == "__main__":
    main()
