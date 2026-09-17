"""Read-only document execution with source, integrity and page coverage gates.

REQ-QA-FULL-ISSUE-INVENTORY-20260916; QAOPT-K01..K06.
Uses the existing flattened three_rules_section index; performs no DDL.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any
import qa_document_integrity
import qa_knowledge_reader_source_gate

VERSION = "qa-document-knowledge-v1"
THREE_RULES = "bf_three_rules_two_systems_20260712"
ACCIDENT = "bf_accident_20260711"
FORMAL_DOCUMENTS = {THREE_RULES: "冀钢炼铁三规二制", ACCIDENT: "高炉事故处理"}
FORMAL_TITLE_ALIASES = {"三规二制": THREE_RULES, "冀钢炼铁三规二制": THREE_RULES,
                        "高炉事故处理": ACCIDENT}
REGULATIONS = ("安全操作规程", "技术操作规程", "设备使用维护规程", "岗位交接班制度", "生产联系确认制")
PAGE_CHARS = 9000
MAX_BLOCK_CHARS = 30000


def canonical_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _integrity(row: dict[str, Any]) -> bool:
    content = str(row.get("content") or "")
    expected = str(row.get("content_hash") or "").lower()
    return bool(content and re.fullmatch(r"[0-9a-f]{64}", expected)
                and expected in {_digest(content), _digest(canonical_text(content))})


def _header(row: dict[str, Any]) -> dict[str, Any] | None:
    text = canonical_text(row.get("enriched_content"))
    chapter = re.search(r"^【岗位/制度】(\d+)\.\s*(.+)$", text, re.M)
    regulation = re.search(r"^【规程类型】(.+)$", text, re.M)
    part = re.search(r"第(\d+)部分$", str(row.get("title") or ""))
    if not chapter or not regulation or not part:
        return None
    return {"chapter_code": int(chapter.group(1)), "chapter": chapter.group(2).strip(),
            "regulation": regulation.group(1).strip(), "part": int(part.group(1))}


def _outcome(answer: str, state: str, code: str, manifests=(), coverage=None) -> dict[str, Any]:
    return {"answer": answer, "answer_route": "verified_document_knowledge",
            "completion": {"schema": VERSION, "terminal_state": state, "reason": code,
                           "semantic_review_required": True, "coverage": coverage or {}},
            "knowledge_manifest": list(manifests), "tool_calls": 0, "model_request_count": 0}


def _manifest(row: dict[str, Any]) -> dict[str, Any]:
    return {key: str(row.get(key) or "") for key in
            ("doc_id", "title", "version", "content_hash", "updated_at")}


def _doc_id(question: str) -> str | None:
    titles = re.findall(r"《([^》]+)》", question)
    if titles:
        resolved = []
        for title in titles:
            source = FORMAL_TITLE_ALIASES.get(title.strip())
            if not source:
                return None
            resolved.append(source)
        return resolved[0] if len(set(resolved)) == 1 else None
    if "三规二制" in question or any(term in question for term in REGULATIONS):
        return THREE_RULES
    if "高炉事故处理" in question:
        return ACCIDENT
    if "高炉工长" in question and "按原文回答" in question and _atomic_selector(question):
        return THREE_RULES
    return None


def _numbered_line(line: str):
    if "|" in line:
        return None  # a table row is never a section boundary
    match = re.match(r"^\s*(\d+(?:[.．]\d+)*)(?:[.．、]\s*|\s*)(.*)$", line)
    if not match:
        return None
    return match.group(1).replace("．", "."), match.group(2).strip()


def _label(value: str) -> str:
    return re.sub(r"[\s，,。；;：:‘’“”\"']", "", value)


def _references(question: str):
    # The book title selects the source; a quoted numbered path selects its
    # subsection. Neither is interpreted as a live-data instruction.
    references = []
    for match in re.finditer(r"“([^”]+)”|\"([^\"]+)\"", question):
        if question[max(0, match.start() - 2):match.start()] == '关于':
            continue  # atomic quoted wording is not another section request
        path = (match.group(1) or match.group(2)).strip()
        leaf = re.split(r"\s*[>＞]\s*", path)[-1]
        ref = _numbered_line(leaf)
        if ref and ref not in references:
            references.append(ref)
    return references


def _reference(question: str):
    references = _references(question)
    return references[0] if references else None


def _atomic_selector(question: str) -> str | None:
    match = re.search(r"关于“(.+)”需要记住", question)
    return match.group(1).strip() if match else None


def _scope_question(question):
    match = re.search(r'关于“(.+)”需要记住', question)
    if not match:
        return question
    # Quoted clause words are evidence references, not new roles/filters.
    return question[:match.start(1)] + ' ' * len(match.group(1)) + question[match.end(1):]


def _negative_regulation_pattern():
    term = '(?:' + '|'.join(re.escape(value) for value in REGULATIONS) + ')'
    return (r'(?:不要|不需要|不引用|不使用|别用|别引用|排除|不包括|不含|不是)'
            r'\s*(?:(?:引用|使用|查阅|读取|按|依据|查询)\s*)?'
            '(?P<terms>' + term + '(?:' + r'\s*[、,，和及与]\s*' + term + ')*)')


class DocumentScopeError(ValueError):
    pass


def _chapter_catalog(indexed):
    chapters = set()
    for raw in indexed:
        match = re.search(r'^【岗位/制度】(\d+)\.\s*(.+)$', canonical_text(dict(raw).get('enriched_content')), re.M)
        if match and len(match.group(1)) <= 3:
            chapters.add((int(match.group(1)), match.group(2).strip()))
    return sorted(chapters)


def _requested_chapters(question, chapters):
    """Resolve the complete bounded explicit scope, never silently drop a code."""
    question = re.sub(_negative_regulation_pattern(), lambda match: ' ' * len(match.group(0)),
                      _scope_question(question))
    requested = {name for _, name in chapters if name in question}
    if not requested:
        requested = {name for _, name in chapters if len(name.removeprefix('高炉')) >= 3
                     and name.removeprefix('高炉') in question}
    if not requested and '工长' in question:
        requested = {name for _, name in chapters if name.endswith('工长')}
        if len(requested) > 1:
            raise DocumentScopeError('chapter_role_ambiguous')
    aliases = {}
    for _, name in chapters:
        for alias in (name, name.removeprefix('高炉')):
            if len(alias) >= 3 or alias == '工长':
                aliases.setdefault(alias, set()).add(name)
    role_pattern = '|'.join(re.escape(alias) for alias in sorted(aliases, key=lambda value: (-len(value), value)))
    pattern = (r'第\s*(?P<start>\d+)\s*(?:章\s*)?(?:至|到|[-—~～])\s*(?:第\s*)?(?P<end>\d+)\s*章'
               r'|第\s*(?P<codes>\d+(?:\s*[、,，和及]\s*(?:第\s*)?\d+)*)\s*章')
    references = list(re.finditer(pattern, question))
    if len(references) > 64:
        raise DocumentScopeError('chapter_request_exceeds_limit')
    available = {code for code, _ in chapters}
    for match in references:
        raw_codes = ([match.group('start'), match.group('end')] if match.group('start')
                     else re.findall(r'\d+', match.group('codes')))
        if len(raw_codes) > 64 or any(len(value) > 3 for value in raw_codes):
            raise DocumentScopeError('chapter_unknown')
        codes = [int(value) for value in raw_codes]
        if match.group('start'):
            if codes[0] > codes[1]:
                raise DocumentScopeError('chapter_range_invalid')
            if codes[1] - codes[0] >= 64:
                raise DocumentScopeError('chapter_unknown')
            codes = list(range(codes[0], codes[1] + 1))
        if any(code not in available for code in codes):
            raise DocumentScopeError('chapter_unknown')
        names = {name for code, name in chapters if code in codes}
        if role_pattern:
            before = re.search('(' + role_pattern + r')\s*(?:的\s*)?$', question[:match.start()])
            after = re.match(r'^\s*(?:的\s*)?(' + role_pattern + ')', question[match.end():])
            for attached in (before, after):
                if attached and not aliases[attached.group(1)].intersection(names):
                    raise DocumentScopeError('chapter_reference_conflict')
        requested.update(names)
    return sorted(requested)


def _scope_error(intro, manifest, error):
    messages = {'chapter_unknown': '所选范围含未核验的章节编号，请核对；未省略未知章节后标为完成。',
                'chapter_reference_conflict': '章节编号与相邻岗位名称不一致，请确认准确范围；未擅自选其中一个。',
                'chapter_role_ambiguous': '工长岗位存在多个范围，请指定准确岗位。',
                'chapter_range_invalid': '章节范围起止倒置，请确认准确范围。',
                'chapter_request_exceeds_limit': '章节选择超出受控上限，请缩小范围。',
                'regulation_scope_conflict': '同一范围的规程同时被要求和排除，请确认准确范围。'}
    return _outcome(intro + messages[str(error)], 'needs_clarification', str(error), [manifest])


def _regulation_scope(question, roles):
    text = _scope_question(question)
    for role in roles:
        if role not in REGULATIONS:
            continue
        other = '|'.join(re.escape(term) for term in REGULATIONS if term != role)
        # "岗位交接班制度的安全操作规程": the first token names the
        # chapter, rather than requesting an additional regulation.
        text = re.sub(re.escape(role) + r'(?=\s*(?:的|中|中的)?\s*(?:' + other + '))',
                      lambda match: ' ' * len(match.group(0)), text)
    excluded = set()
    def remove_negative(match):
        excluded.update(term for term in REGULATIONS if term in match.group('terms'))
        return ' ' * len(match.group(0))
    positive_text = re.sub(_negative_regulation_pattern(), remove_negative, text)
    included = {term for term in REGULATIONS if term in positive_text}
    if included.intersection(excluded):
        raise DocumentScopeError('regulation_scope_conflict')
    return {'include': included or None, 'exclude': excluded}


def _regulation_allowed(regulation, scope):
    return regulation not in scope['exclude'] and (scope['include'] is None or regulation in scope['include'])


def _regulation_scopes(question, requested, chapters):
    clauses = re.split(r'[;；]|同时|以及|并且', _scope_question(question))
    if len(clauses) < 2 or len(requested) < 2:
        return {name: _regulation_scope(question, requested) for name in requested}
    scopes = {}
    for clause in clauses:
        names = set(_requested_chapters(clause, [(code, name) for code, name in chapters if name in requested]))
        if not names:
            continue
        scope = _regulation_scope(clause, names)
        for name in names:
            if name not in scopes:
                scopes[name] = scope
            else:
                previous = scopes[name]
                explicit = (previous['include'] or set()) | (scope['include'] or set())
                excluded = previous['exclude'] | scope['exclude']
                if explicit.intersection(excluded):
                    raise DocumentScopeError('regulation_scope_conflict')
                included = None if previous['include'] is None or scope['include'] is None else explicit
                scopes[name] = {'include': included, 'exclude': excluded}
    for name in set(requested) - set(scopes):
        scopes[name] = _regulation_scope(question, [name])
    return scopes


def _chapter_coverage(result, requested, selected, scopes):
    returned = {item['chapter'] for item in selected}
    missing = sorted(set(requested) - returned)
    missing_types = {}
    for name in requested:
        types = {item['regulation'] for item in selected if item['chapter'] == name}
        absent = sorted((scopes[name]['include'] or set()) - types)
        if absent:
            missing_types[name] = absent
    result['completion']['coverage'].update(requested_chapters=len(requested),
                                             available_chapters=len(returned), missing_chapters=missing,
                                             missing_regulations_by_chapter=missing_types,
                                             excluded_regulations_by_chapter={name: sorted(scopes[name]['exclude']) for name in requested})
    if missing or missing_types:
        labels = [name + ' / ' + '、'.join(types) for name, types in missing_types.items()]
        labels.extend(name for name in missing if name not in missing_types)
        result['answer'] += '\n\n以下请求范围没有已核验条款：' + '；'.join(labels) + '。未将其省略后判为全部完成。'
        if result['completion']['terminal_state'] == 'completed':
            result['completion'].update(terminal_state='partial', reason='requested_chapters_partially_available')
    return result


def _original_atomic(conn, question, intro, manifest, indexed=None, selected_roles=None):
    selector = _atomic_selector(question)
    if not selector:
        return None
    wanted = _label(selector)
    if len(wanted) < 2:
        return _outcome(intro + "条款引用过短，无法唯一识别原文，请补充原句。", "needs_clarification", "atomic_reference_too_short", [manifest])
    parent = _reference(question)
    rows = [row for row in indexed if row.get('chunk_type') == 'three_rules_atomic'] if indexed is not None else conn.execute(
        "SELECT chunk_id, doc_id, content, enriched_content, content_hash, authority_level "
        "FROM rag_chunk WHERE doc_id = ? AND chunk_type = ? ORDER BY chunk_id LIMIT 12001",
        (THREE_RULES, "three_rules_atomic"),
    ).fetchall()
    if len(rows) > 12000:
        return _outcome(intro + "条款索引超出受控上限，未截取少量片段冒充完整匹配。", "dependency_blocked", "atomic_index_exceeds_limit", [manifest])
    roles = set()
    for raw in rows:
        role = re.search(r'^【岗位/制度】\d+\.\s*(.+)$', canonical_text(dict(raw).get('enriched_content')), re.M)
        if role:
            roles.add(role.group(1).strip())
    requested_roles = selected_roles if selected_roles is not None else [role for role in roles if role in question]
    if len(requested_roles) != 1:
        return _outcome(intro + "请明确唯一岗位后读取所引条款，未借用其他岗位的同句原文。",
                        "needs_clarification", "atomic_role_unresolved", [manifest])
    scope = _regulation_scope(question, requested_roles)
    matches = {}
    for raw in rows:
        row = dict(raw)
        header = canonical_text(row.get("enriched_content"))
        role = re.search(r"^【岗位/制度】\d+\.\s*(.+)$", header, re.M)
        regulation = re.search(r"^【规程类型】(.+)$", header, re.M)
        path = re.search(r"^【层级路径】(.+)$", header, re.M)
        if not role or role.group(1).strip() != requested_roles[0] or not regulation:
            continue
        if not _regulation_allowed(regulation.group(1).strip(), scope):
            continue
        path_parts = [_numbered_line(part) for part in re.split(r'\s*[>＞]\s*', path.group(1))] if path else []
        if parent and not any(part and part[0] == parent[0] and _label(part[1]).startswith(_label(parent[1]))
                              for part in path_parts):
            continue
        content = canonical_text(row.get("content")).strip()
        parsed = _numbered_line(content.split("\n", 1)[0])
        wording = _label(parsed[1] if parsed else content)
        if not wording.startswith(wanted):
            continue
        if row.get("authority_level") != "knowledge_doc" or not _integrity(row):
            return _outcome(intro + "匹配条款的来源或哈希未通过核验，未生成正式答案。", "dependency_blocked", "atomic_integrity_unverified", [manifest])
        raw_wording = parsed[1] if parsed else content
        named_term = _label(re.split(r"[:：]", raw_wording, maxsplit=1)[0])
        rank = 3 if wording == wanted else (2 if named_term == wanted else 1)
        matches[(regulation.group(1).strip(), content)] = (rank, row)
    requested_types = [term for term in REGULATIONS if term in (scope['include'] or set())]
    if len(requested_types) > 1:
        chosen, missing, ambiguous = [], [], []
        for requested_type in requested_types:
            candidates = [(content, rank, row) for (regulation, content), (rank, row) in matches.items()
                          if regulation == requested_type]
            if not candidates:
                missing.append(requested_type)
                continue
            best = max(item[1] for item in candidates)
            candidates = [item for item in candidates if item[1] == best]
            if len(candidates) != 1:
                ambiguous.append(requested_type)
            else:
                content, _, row = candidates[0]
                chosen.append((requested_type, content, row))
        coverage = {'requested_regulations': requested_types, 'excluded_regulations': sorted(scope['exclude']),
                    'missing_regulations': missing, 'ambiguous_regulations': ambiguous,
                    'matched_scopes': len(chosen), 'table_blocks_preserved': True}
        if not chosen:
            return _outcome(intro + '所选岗位、规程及层级下未唯一确认所引原文，请核对范围和完整原句；未借用其他范围。',
                            'needs_clarification', 'atomic_reference_ambiguous' if ambiguous else 'atomic_reference_not_found',
                            [manifest], coverage)
        if any(len(content) > MAX_BLOCK_CHARS for _, content, _ in chosen):
            return _outcome(intro + '完整条款或表格超出受控范围，未裁切原文。',
                            'dependency_blocked', 'atomic_block_exceeds_limit', [manifest], coverage)
        pages, chars = [[]], 0
        for item in chosen:
            size = len(item[1])
            if pages[-1] and chars + size > PAGE_CHARS:
                pages.append([])
                chars = 0
            pages[-1].append(item)
            chars += size
        page_match = re.search(r'第\s*(\d+)\s*页', question)
        page = int(page_match.group(1)) if page_match and len(page_match.group(1)) <= 3 else (-1 if page_match else 1)
        if not 1 <= page <= len(pages):
            return _outcome(intro + f'可用页码为1–{len(pages)}，请核对页码。', 'needs_clarification',
                            'page_out_of_range', [manifest], coverage)
        returned = pages[page - 1]
        body = '\n\n'.join(f'【{requested_roles[0]} / {regulation}】\n' + content for regulation, content, _ in returned)
        gap = ('\n\n未找到所引条款的规程：' + '、'.join(missing)) if missing else ''
        gap += ('\n\n所引条款仍有歧义的规程：' + '、'.join(ambiguous)) if ambiguous else ''
        coverage.update(chunk_ids=[str(row['chunk_id']) for _, _, row in returned],
                        pages=len(pages), page=page, returned_scopes=len(returned))
        if len(pages) > 1:
            gap += f'\n\n原文共{len(pages)}页，本次第{page}页；表格未裁切，其他页面须分别读取，未将单页标为全部完成。'
        return _outcome(intro + '以下为各所选规程中唯一匹配的完整原文条款：\n\n' + body + gap,
                        'partial' if missing or ambiguous or len(pages) > 1 else 'completed', 'verified_original_atomic_scopes', [manifest], coverage)
    if matches:
        best_rank = max(value[0] for value in matches.values())
        matches = {key: value for key, value in matches.items() if value[0] == best_rank}
    if len(matches) != 1:
        return _outcome(intro + "所选岗位、规程或层级下未唯一确认所引原文，请核对范围和完整原句；未借用其他范围。", "needs_clarification", "atomic_reference_ambiguous" if matches else "atomic_reference_not_found", [manifest])
    (regulation, content), (_, row) = next(iter(matches.items()))
    if len(content) > MAX_BLOCK_CHARS:
        return _outcome(intro + "完整条款或表格超出受控范围，未裁切原文。", "dependency_blocked", "atomic_block_exceeds_limit", [manifest])
    return _outcome(intro + f"【{requested_roles[0]} / {regulation}】\n以下为唯一匹配的完整原文条款：\n\n" + content,
                    "completed", "verified_original_atomic", [manifest],
                    {"chunk_id": str(row["chunk_id"]), "matched_scopes": 1, "table_blocks_preserved": True,
                     'requested_regulations': requested_types, 'excluded_regulations': sorted(scope['exclude'])})


def _original_subsection(selected, reference, intro, manifest):
    code, label = reference
    groups = {}
    for item in selected:
        groups.setdefault((item["chapter_code"], item["chapter"], item["regulation"]), []).append(item)
    matches = []
    for (_, chapter, regulation), pieces in groups.items():
        lines = "\n".join(canonical_text(item["content"]) for item in pieces).split("\n")
        for index, line in enumerate(lines):
            parsed = _numbered_line(line)
            if not parsed or parsed[0] != code or (label and _label(parsed[1]) != _label(label)):
                continue
            end = len(lines)
            for next_index in range(index + 1, len(lines)):
                # Reviewed source anomaly: this heading omits its section 11
                # number. It precedes 11.1, and is not part of section 10.
                if code.split(".")[0] == "10" and lines[next_index].strip() == "生铁与原燃料标准":
                    end = next_index
                    break
                next_parsed = _numbered_line(lines[next_index])
                if next_parsed and not next_parsed[0].startswith(code + "."):
                    end = next_index
                    break
            matches.append((chapter, regulation, "\n".join(lines[index:end]).strip()))
    if len(matches) != 1:
        reason = "subsection_ambiguous" if matches else "subsection_not_found"
        return _outcome(intro + "尚未唯一确认该编号及标题的原文章节。请补充规程类型或核对章节路径；未用同编号的其他规程替代。",
                        "needs_clarification", reason, [manifest])
    chapter, regulation, content = matches[0]
    if len(content) > MAX_BLOCK_CHARS:
        return _outcome(intro + "所选章节含超长完整段落或表格，请按更细的子章节读取，未裁切原文。",
                        "dependency_blocked", "subsection_exceeds_limit", [manifest])
    return _outcome(intro + f"【{chapter} / {regulation} / {code}】\n以下为对应原文，未补写其他章节：\n\n" + content,
                    "completed", "verified_original_subsection", [manifest],
                    {"section_code": code, "matched_scopes": 1, "table_blocks_preserved": True})


def _original_subsections(selected, references, intro, manifest):
    if len(references) > 8:
        return _outcome(intro + '本次明确指定的章节超过8个，请分批读取；未只回答第一章就标为全部完成。',
                        'needs_clarification', 'subsection_request_limit', [manifest])
    outcomes = [_original_subsection(selected, reference, '', manifest) for reference in references]
    answer = intro + '\n\n'.join(f'【子任务 {index + 1}：{references[index][0]} {references[index][1]}】\n' + item['answer']
                                  for index, item in enumerate(outcomes))
    if len(answer) > MAX_BLOCK_CHARS:
        return _outcome(intro + '所选多个完整章节总长度超出受控范围，请分批读取；未裁切条款、表格或静默遗漏章节。',
                        'needs_clarification', 'subsection_combined_limit', [manifest])
    complete = all(item['completion']['terminal_state'] == 'completed' for item in outcomes)
    any_completed = any(item['completion']['terminal_state'] == 'completed' for item in outcomes)
    state = 'completed' if complete else 'partial' if any_completed else 'needs_clarification'
    result = _outcome(answer, state, 'verified_original_subsections' if complete else 'subsection_subtasks_incomplete', [manifest],
                      {'requested_subsections': len(references), 'completed_subsections': sum(item['completion']['terminal_state'] == 'completed' for item in outcomes),
                       'table_blocks_preserved': True})
    result['completion'].update(complete=complete, subsection_subtasks=[item['completion'] for item in outcomes])
    return result


def _execute_document_question_in_snapshot(conn: Any, question: str, plan: dict[str, Any], snapshot=None) -> dict[str, Any] | None:
    """Only pure document tasks; compound tasks stay in their source plan."""
    if plan.get("intents") != ["document_knowledge"]:
        return None
    doc_id = _doc_id(question)
    if not doc_id:
        return _outcome("尚未确认所指文档的权威原文。请提供准确书名及岗位/章节；不能用聊天、报表或通用知识补写正式条款。",
                        "needs_clarification", "document_reference_unresolved")
    row = snapshot['document'] if snapshot is not None else conn.execute(
        "SELECT doc_id, title, version, authority_level, content_hash, updated_at, full_text "
        "FROM rag_document WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    doc = dict(row or {})
    if (doc.get("title") != FORMAL_DOCUMENTS[doc_id] or doc.get("authority_level") != "knowledge_doc"
            or not _integrity({"content": doc.get("full_text"), "content_hash": doc.get("content_hash")})):
        return _outcome("所指文档的原文、来源或版本完整性尚未通过核验，未生成正式制度答案。",
                        "dependency_blocked", "document_integrity_unverified")
    manifest = _manifest(doc)
    intro = f"来源：《{doc['title']}》；版本 {manifest['version']}；更新 {manifest['updated_at']}。\n"
    if doc_id == THREE_RULES:
        indexed = snapshot['chunks'] if snapshot is not None else conn.execute(
            "SELECT chunk_type, content, content_hash, authority_level, enriched_content FROM rag_chunk "
            "WHERE doc_id = ? AND chunk_type IN (?, ?, ?) ORDER BY chunk_id LIMIT 15001",
            (doc_id, 'three_rules_atomic', 'three_rules_section', 'three_rules_topic'),
        ).fetchall()
        gate = qa_document_integrity.inspect(str(doc.get('full_text') or ''), [dict(row) for row in indexed])
        if not gate['verified']:
            return _outcome(intro + "权威原文与章节索引的独立完整性核验未通过，可能有缺失或来源不一致；未将现有片段当作完整正式制度。",
                            'dependency_blocked', gate['reason'], [manifest], {'authority_index': gate})
        try:
            selected_roles = _requested_chapters(question, _chapter_catalog(indexed))
            atomic_result = _original_atomic(conn, question, intro, manifest, indexed if snapshot is not None else None,
                                             selected_roles=selected_roles)
        except DocumentScopeError as exc:
            return _scope_error(intro, manifest, exc)
        if atomic_result is not None:
            return atomic_result
    if doc_id == ACCIDENT:
        body = canonical_text(doc.get("full_text"))
        if len(body) > MAX_BLOCK_CHARS:
            return _outcome(intro + "原文超出单页安全范围，需先建立章节索引，未裁切表格或伪称全文完成。",
                            "dependency_blocked", "chapter_index_required", [manifest])
        return _outcome(intro + "以下为已核验原文，未补写现场判断：\n\n" + body,
                        "completed", "verified_original_document", [manifest], {"documents": 1})
    # section pieces are already present in rag_chunk on production.  Fetch the
    # complete bounded document scope, rather than top-k pieces across sources.
    rows = [row for row in snapshot['chunks'] if row.get('chunk_type') == 'three_rules_section'] if snapshot is not None else conn.execute(
        "SELECT chunk_id, doc_id, title, content, enriched_content, content_hash, authority_level "
        "FROM rag_chunk WHERE doc_id = ? AND chunk_type = ? ORDER BY chunk_id LIMIT 2001",
        (doc_id, "three_rules_section")
    ).fetchall()
    if not rows or len(rows) > 2000:
        return _outcome(intro + "章节索引缺失或超出受控上限，未将少量检索片段当作完整制度。",
                        "dependency_blocked", "section_index_incomplete", [manifest])
    pieces = []
    for raw in rows:
        item = dict(raw)
        header = _header(item)
        if not header or item.get("authority_level") != "knowledge_doc" or not _integrity(item):
            return _outcome(intro + "章节顺序或片段完整性未通过核验，未拼接正式条款。",
                            "dependency_blocked", "section_integrity_unverified", [manifest])
        pieces.append(item | header)
    chapters = sorted({(item["chapter_code"], item["chapter"]) for item in pieces})
    try:
        requested = _requested_chapters(question, chapters)
        regulation_scopes = _regulation_scopes(question, requested, chapters)
        global_scope = _regulation_scope(question, []) if not requested else None
    except DocumentScopeError as exc:
        return _scope_error(intro, manifest, exc)
    selected = [item for item in pieces if not requested or item["chapter"] in requested]
    if requested:
        selected = [item for item in selected if _regulation_allowed(item['regulation'], regulation_scopes[item['chapter']])]
    else:
        selected = [item for item in selected if _regulation_allowed(item['regulation'], global_scope)]
    if not selected:
        return _outcome(intro + "该岗位/规程组合没有已核验原文；未用其他岗位或报表替代。",
                        "dependency_blocked", "requested_scope_missing", [manifest])
    if not requested and not any(term in question for term in ("全文", "整本", "全书", "所有岗位", "全部岗位", "目录")):
        names = "；".join(f"{code}. {name}" for code, name in chapters)
        return _outcome(intro + "请指定岗位或章节后读取对应条款。已核验目录：\n" + names,
                        "needs_clarification", "chapter_selection_required", [manifest])
    if "目录" in question and not any(term in question for term in ("全文", "原文")):
        return _outcome(intro + "\n" + "\n".join(f"{code}. {name}" for code, name in chapters),
                        "completed", "verified_chapter_catalog", [manifest], {"chapters": len(chapters)})
    selected.sort(key=lambda x: (x["chapter_code"], REGULATIONS.index(x["regulation"]) if x["regulation"] in REGULATIONS else -1, x["part"]))
    groups: dict[tuple[int, str], list[int]] = {}
    for item in selected:
        groups.setdefault((item["chapter_code"], item["regulation"]), []).append(item["part"])
    if any(parts != list(range(1, len(parts) + 1)) for parts in groups.values()):
        return _outcome(intro + "所选章节存在缺页或重复片段，未把拼接结果标为完整。",
                        "dependency_blocked", "section_parts_not_contiguous", [manifest])
    scope_gate = qa_document_integrity.inspect_selected_scope(selected, [dict(row) for row in indexed])
    if not scope_gate['verified']:
        return _outcome(intro + "所选岗位/规程的章节内容与其他已核验原文索引不一致，可能缺少条款；未将当前片段标为完整。",
                        'dependency_blocked', scope_gate['reason'], [manifest], {'selected_scope': scope_gate})
    references = _references(question)
    if len(references) > 1:
        return _chapter_coverage(_original_subsections(selected, references, intro, manifest), requested, selected, regulation_scopes)
    if references:
        return _chapter_coverage(_original_subsection(selected, references[0], intro, manifest), requested, selected, regulation_scopes)
    pages: list[list[dict[str, Any]]] = [[]]
    chars = 0
    for item in selected:
        size = len(canonical_text(item["content"]))
        if size > MAX_BLOCK_CHARS:
            return _outcome(intro + "存在超长完整表格/片段，需独立导出，未裁切其行或列。",
                            "dependency_blocked", "whole_block_exceeds_limit", [manifest])
        if pages[-1] and chars + size > PAGE_CHARS:
            pages.append([])
            chars = 0
        pages[-1].append(item)
        chars += size
    match = re.search(r"第\s*(\d+)\s*页", question)
    page = int(match.group(1)) if match else 1
    if not 1 <= page <= len(pages):
        return _outcome(intro + f"可用页码为 1–{len(pages)}，请核对页码。", "needs_clarification", "page_out_of_range", [manifest])
    body = "\n\n".join(f"【{item['chapter']} / {item['regulation']} / 第{item['part']}部分】\n" + canonical_text(item["content"]) for item in pages[page - 1])
    more = f"\n\n原文共 {len(pages)} 页，本次第 {page} 页；沿用同一书名及岗位/规程，并指定第 {page + 1} 页可继续读取。全文尚未全部展示。" if len(pages) > 1 and page < len(pages) else (f"\n\n原文共 {len(pages)} 页，本次为最后一页；此前页面须分别读取。" if len(pages) > 1 else "")
    result = _outcome(intro + "以下为所选范围的原文，未补写正式条款：\n\n" + body + more,
                    "partial" if len(pages) > 1 else "completed", "verified_original_page", [manifest],
                    {"pages": len(pages), "page": page, "selected_parts": len(selected), "returned_parts": len(pages[page - 1]), "table_blocks_preserved": True})
    return _chapter_coverage(result, requested, selected, regulation_scopes)


def lookup_policy_blocked() -> dict[str, Any]:
    return _outcome('本轮禁止调用工具或查询数据库，正式制度原文未读取；未使用通用知识补写正式条款。'
                    '如需分析，可提供需要分析的原文，或明确允许资料读取。',
                    'dependency_blocked', 'document_lookup_policy_blocked')


def execute_document_question(conn: Any, question: str, plan: dict[str, Any]) -> dict[str, Any] | None:
    """Production entry: freeze every formal source field in one verified SELECT."""
    if plan.get('intents') != ['document_knowledge']:
        return None
    if plan.get('all_tools_disabled'):
        return lookup_policy_blocked()
    if _doc_id(question) != THREE_RULES:
        return _execute_document_question_in_snapshot(conn, question, plan)
    try:
        row = conn.execute(qa_knowledge_reader_source_gate.SNAPSHOT_SQL, (THREE_RULES,)).fetchone()
        snapshot = dict(row or {})
        gate = qa_knowledge_reader_source_gate.verify(snapshot)
    except qa_knowledge_reader_source_gate.ReaderSourceError as exc:
        return _outcome('制度原书范围、来源绑定或完整检索索引尚未通过核验；未将现有片段标为完整原文，也未用其他知识补写。',
                        'dependency_blocked', str(exc), coverage={'original_source_scope_verified': False})
    except Exception:
        return _outcome('制度原书来源绑定暂不可读，未用旧片段或聊天补写正式条款。',
                        'dependency_blocked', 'original_source_snapshot_unavailable',
                        coverage={'original_source_scope_verified': False})
    result = _execute_document_question_in_snapshot(None, question, plan, snapshot=snapshot)
    if result:
        result['completion']['coverage']['original_source'] = gate
    return result
