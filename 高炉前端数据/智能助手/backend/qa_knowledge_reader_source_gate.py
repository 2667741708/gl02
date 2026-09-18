"""Fixed original-source reader projections; no raw candidate file or model needed."""
from __future__ import annotations

import hashlib
import json
import qa_knowledge_source_binding as binding

DOC_SHA = 'a07d70ea803bf222a6da5cf2788357d98c1256d99bd69f7f8589cb82fd808cfd'
CHUNKS_SHA = 'e217376def1b6df37b667c709cbf541d83da4b3475ab0bfd56d28d22c0743970'
PLAN_SHA = '7ca28451af71cc389076bba21774f75540597a4e926ed4e0a0bf9280dd7dd16d'
RELEASE_ID = 'qa-source-keyword-20260917-r2'
DOC_FIELDS = ('doc_id', 'version', 'full_text', 'content_hash')
CHUNK_FIELDS = ('chunk_id', 'doc_id', 'parent_chunk_id', 'title', 'content', 'enriched_content',
                'summary', 'keywords_json', 'entities_json', 'phenomenon_json', 'parameter_names_json',
                'chunk_type', 'token_count', 'knowledge_category', 'task_scope_json', 'authority_level',
                'source_priority', 'content_hash', 'search_text')

# One PostgreSQL statement provides one MVCC snapshot. No before archive/vector
# payload is returned. LIMIT has a sentinel; over-limit sources cannot pass.
SNAPSHOT_SQL = (
    "SELECT to_jsonb(d) AS document,COALESCE((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.chunk_id) "
    "FROM (SELECT * FROM rag_chunk WHERE doc_id=d.doc_id ORDER BY chunk_id LIMIT 10001) c),'[]'::jsonb) AS chunks,"
    "(SELECT to_jsonb(b) FROM qa_knowledge_source_bindings b WHERE b.doc_id=d.doc_id) AS binding,"
    "(SELECT jsonb_build_object('release_id',r.release_id,'doc_id',r.doc_id,'state',r.state,"
    "'manifest_sha256',r.manifest_sha256,'plan_sha256',r.plan_sha256,'after_snapshot_sha256',r.after_snapshot_sha256) "
    "FROM qa_knowledge_source_releases r JOIN qa_knowledge_source_bindings b ON b.release_id=r.release_id "
    "WHERE b.doc_id=d.doc_id) AS release,"
    "(SELECT count(*) FROM rag_chunk_embedding e JOIN rag_chunk c ON c.chunk_id=e.chunk_id "
    "WHERE c.doc_id=d.doc_id) AS embedding_count FROM rag_document d WHERE d.doc_id=?"
)


class ReaderSourceError(ValueError):
    pass


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def projection(document, chunks):
    if (not isinstance(document, dict) or not isinstance(chunks, list) or not chunks
            or len(chunks) > 10000 or not isinstance(document.get('full_text'), str)
            or len(document['full_text']) > 2000000):
        raise ReaderSourceError('original_source_snapshot_bounds')
    if any(not isinstance(row, dict) for row in chunks):
        raise ReaderSourceError('original_source_chunk_type')
    try:
        doc = {key: document[key] for key in DOC_FIELDS}
        rows = [{key: row[key] for key in CHUNK_FIELDS} for row in chunks]
        if any(not isinstance(row['chunk_id'], str) for row in rows):
            raise ReaderSourceError('original_source_chunk_id_type')
        rows.sort(key=lambda row: row['chunk_id'])
        return digest(doc), digest(rows)
    except (KeyError, TypeError, ValueError):
        raise ReaderSourceError('original_source_projection_invalid') from None


def verify(snapshot):
    """Check fixed content, retrieval fields, manifest and applied release together."""
    if not isinstance(snapshot, dict):
        raise ReaderSourceError('original_source_snapshot_missing')
    doc, chunks = snapshot.get('document'), snapshot.get('chunks')
    source, release = snapshot.get('binding'), snapshot.get('release')
    if not isinstance(source, dict) or not isinstance(release, dict):
        raise ReaderSourceError('original_source_binding_unavailable')
    if (source.get('doc_id') != binding.DOC_ID or source.get('release_id') != RELEASE_ID
            or source.get('authority_sha256') != binding.AUTHORITY_SHA
            or source.get('manifest_sha256') != binding.MANIFEST_SHA
            or release.get('release_id') != RELEASE_ID or release.get('doc_id') != binding.DOC_ID
            or release.get('state') != 'applied' or release.get('manifest_sha256') != binding.MANIFEST_SHA
            or release.get('plan_sha256') != PLAN_SHA):
        raise ReaderSourceError('original_source_release_identity_unverified')
    if type(snapshot.get('embedding_count')) is not int or snapshot['embedding_count'] != 0:
        raise ReaderSourceError('original_source_keyword_vectors_unverified')
    actual_doc, actual_chunks = projection(doc, chunks)
    if actual_doc != DOC_SHA or actual_chunks != CHUNKS_SHA:
        raise ReaderSourceError('original_source_fixed_projection_mismatch')
    path = doc.get('source_file')
    if (doc.get('title') != '冀钢炼铁三规二制' or doc.get('authority_level') != 'knowledge_doc'
            or not isinstance(path, str) or not path or any(row.get('source_file') != path for row in chunks)):
        raise ReaderSourceError('original_source_provenance_unverified')
    try:
        manifest_text = source.get('manifest_text')
        if not isinstance(manifest_text, str):
            raise ReaderSourceError('original_source_manifest_missing')
        manifest = binding.load_manifest(manifest_text.encode('utf-8'))
        gate = binding._chunk_gate(manifest, chunks, database=True)
        complete_snapshot = {'document': doc, 'chunks': sorted(chunks, key=lambda row: row['chunk_id']),
                             'embeddings': [], 'binding': source}
        if digest(complete_snapshot) != release.get('after_snapshot_sha256'):
            raise ReaderSourceError('original_source_after_snapshot_drift')
    except binding.SourceBindingError:
        raise ReaderSourceError('original_source_manifest_or_content_unverified') from None
    return dict(gate, database_snapshot_verified=True, original_source_scope_verified=True,
                manifest_sha256=binding.MANIFEST_SHA, authority_sha256=binding.AUTHORITY_SHA,
                document_projection_sha256=DOC_SHA, retrieval_projection_sha256=CHUNKS_SHA,
                release_id=RELEASE_ID, model_calls=0, semantic_verified=False)
