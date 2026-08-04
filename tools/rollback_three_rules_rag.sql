\set ON_ERROR_STOP on
BEGIN;
DELETE FROM bf_assistant.rag_chunk_embedding
WHERE chunk_id IN (
  SELECT chunk_id FROM bf_assistant.rag_chunk
  WHERE doc_id = 'bf_three_rules_two_systems_20260712'
);
DELETE FROM bf_assistant.rag_chunk
WHERE doc_id = 'bf_three_rules_two_systems_20260712';
DELETE FROM bf_assistant.rag_document
WHERE doc_id = 'bf_three_rules_two_systems_20260712';
COMMIT;

SELECT 'remaining_documents=' || count(*)
FROM bf_assistant.rag_document
WHERE doc_id = 'bf_three_rules_two_systems_20260712';
SELECT 'remaining_chunks=' || count(*)
FROM bf_assistant.rag_chunk
WHERE doc_id = 'bf_three_rules_two_systems_20260712';
