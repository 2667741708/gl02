"""HTTP handlers for persisted five-minute, on-demand single-condition analysis.

The large proxy contains long in-browser source lines, so these handlers are kept in
an isolated module and installed on its request handler at startup.

Corresponding requirement:
REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import diagnosis_model_review


def install_handler(handler_class: type, runtime: dict[str, Any]) -> None:
    """Install GET/retry methods using server-owned context and runtime callbacks."""

    def handle_get(self: Any, query: str) -> None:
        if not runtime["DIAGNOSIS_AI_ANALYSIS_ENABLED"]:
            self.send_json({"ok": True, "enabled": False})
            return
        params = parse_qs(query)
        target_label = str((params.get("label") or [""])[0]).strip()
        if target_label not in diagnosis_model_review.DIAGNOSIS_LABELS:
            self.send_json({"ok": False, "error": "请选择有效的8类炉况"}, status=400)
            return
        if str((params.get("fixture") or [""])[0]).strip():
            try:
                canonical = self.canonical_review_context(params)
                batch = diagnosis_model_review.build_fixture_five_minute_analysis(
                    canonical,
                    bucket_minutes=runtime["DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES"],
                )
                context = diagnosis_model_review.normalize_five_minute_context(
                    canonical,
                    [],
                    bucket_minutes=runtime["DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES"],
                )
                row = {
                    "generation_state": "completed",
                    "analyses": batch["analyses"],
                    "attempt_count": 1,
                    "completed_at": batch["created_at"],
                }
                result = runtime["public_five_minute_analysis"](
                    context, row, target_label
                )
                self.send_json({"ok": True, "enabled": True, "analysis": result})
            except PermissionError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=403)
            except Exception as exc:  # noqa: BLE001
                self.send_json({"ok": False, "error": str(exc)}, status=503)
            return

        try:
            context = runtime["current_five_minute_analysis_context"](target_label)
            store = runtime["five_minute_analysis_store"]()
            row = store.get_ai_analysis(
                furnace_id=str(context["furnace_id"]),
                bucket_ts=context["bucket_ts"],
                prompt_version=diagnosis_model_review.single_condition_prompt_version(
                    target_label
                ),
            )
            if row is None or (
                row.get("generation_state") == "failed"
                and runtime["_analysis_retry_due"](row)
            ):
                runtime["queue_five_minute_analysis"](target_label=target_label)
            result = runtime["public_five_minute_analysis"](
                context, row, target_label
            )
            status = 200 if result["state"] in {"completed", "failed"} else 202
            self.send_json(
                {"ok": True, "enabled": True, "analysis": result}, status=status
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error": "5分钟智能分析暂不可用",
                    "error_type": type(exc).__name__,
                },
                status=503,
            )

    def handle_core_evidence(self: Any, query: str) -> None:
        """Serve the 19-variable curve contract without waiting for model prose."""
        if not runtime["DIAGNOSIS_AI_ANALYSIS_ENABLED"]:
            self.send_json({"ok": True, "enabled": False})
            return
        params = parse_qs(query)
        target_label = str((params.get("label") or [""])[0]).strip()
        if target_label not in diagnosis_model_review.DIAGNOSIS_LABELS:
            self.send_json(
                {"ok": False, "error": "请选择有效的8类炉况"}, status=400
            )
            return
        try:
            result = runtime["current_core_variable_evidence"](target_label)
            self.send_json({"ok": True, "enabled": True, "evidence": result})
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error": "核心变量证据暂不可用",
                    "error_type": type(exc).__name__,
                },
                status=503,
            )

    def handle_retry(self: Any) -> None:
        if not runtime["DIAGNOSIS_AI_ANALYSIS_ENABLED"]:
            self.send_json(
                {"ok": False, "error": "5分钟智能分析未启用"}, status=404
            )
            return
        try:
            body = self.read_json_body()
            target_label = str(body.get("label") or "").strip()
            if target_label not in diagnosis_model_review.DIAGNOSIS_LABELS:
                raise diagnosis_model_review.ModelReviewValidationError(
                    "请选择有效的8类炉况"
                )
            context = runtime["current_five_minute_analysis_context"](target_label)
            store = runtime["five_minute_analysis_store"]()
            row = store.get_ai_analysis(
                furnace_id=str(context["furnace_id"]),
                bucket_ts=context["bucket_ts"],
                prompt_version=diagnosis_model_review.single_condition_prompt_version(
                    target_label
                ),
            )
            if row and row.get("generation_state") == "completed":
                result = runtime["public_five_minute_analysis"](
                    context, row, target_label
                )
                self.send_json({"ok": True, "queued": False, "analysis": result})
                return
            if (
                row
                and row.get("generation_state") == "failed"
                and not runtime["_analysis_retry_due"](row)
            ):
                result = runtime["public_five_minute_analysis"](
                    context, row, target_label
                )
                self.send_json(
                    {
                        "ok": False,
                        "queued": False,
                        "error": "请稍后再重试，避免重复占用模型服务",
                        "analysis": result,
                    },
                    status=429,
                )
                return
            queued = runtime["queue_five_minute_analysis"](
                target_label=target_label, retry_failed=True
            )
            result = runtime["public_five_minute_analysis"](
                context, row, target_label
            )
            if queued:
                result["state"] = "reasoning"
            self.send_json(
                {"ok": True, "queued": queued, "analysis": result}, status=202
            )
        except diagnosis_model_review.ModelReviewValidationError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error": "5分钟智能分析重试失败",
                    "error_type": type(exc).__name__,
                },
                status=503,
            )

    handler_class.handle_diagnosis_ai_analysis_get = handle_get
    handler_class.handle_diagnosis_core_evidence_get = handle_core_evidence
    handler_class.handle_diagnosis_ai_analysis_retry = handle_retry
