# ABC33 canonical score source and legacy archive

## Canonical display contract

When a legacy eight-class diagnosis label overlaps a released ABC33 rule, the production UI must display one source only. For the current mismatch:

| UI concept | Canonical rule | Canonical field | Legacy field |
|---|---|---|---|
| 热制度上行 | ABC33 `B4` 热制度上行风险 | latest aligned `public_bundle.rules[B4].score` with `score_available=true` | diagnosis snapshot `raw_scores.hot` |

Align the ABC33 evaluation to the diagnosis timestamp and prefer the same `source_snapshot_id`. Accept at most 15 minutes old, never newer than the diagnosis snapshot, and require the ABC batch itself to be no more than 20 minutes old against the current wall clock. Preserve `evaluation_id`, `evaluation_ts`, `source_snapshot_id` match state, `catalog_version`, `config_version`, status, relative age, and wall-clock age in source metadata.

If B4 is missing, `needs_data`, non-finite, or outside the timestamp window, display `--`/unavailable. Never fall back to `raw_scores.hot`; fallback would recreate the original mismatch.

## Archive contract

- Keep historical diagnosis rows and `raw_scores.hot` unchanged.
- Expose the prior value only as explicit read-only legacy archive metadata with `used_for_display=false`.
- For existing review-event JSONB columns, keep the original eight legacy score keys unchanged and add the display/source/archive contract below `_display_contract`; old rows without that key remain legacy-only. Do not reuse the same numeric key with a different meaning.
- Do not copy the legacy value into the ABC33 tables, rewrite past review events, or delete backups.
- Do not rename the legacy eight-class engine as ABC33. The main diagnosis label may continue to come from the legacy classifier while the overlapping displayed risk score comes from B4.
- Record the cutover version and deployment backup so an operator can audit which source was displayed at any time.

## Acceptance

Verify the same `evaluation_id`, B4 score, timestamp, catalog/config version, and availability state in `/api/furnace-rules/latest` and `/api/diagnosis-review-context`. Test current, missing, stale, future, non-finite, and `needs_data` cases. Browser checks must prove the abnormal popup and manual-score window show the B4 value or `--`, while the legacy archive remains non-displayed.
