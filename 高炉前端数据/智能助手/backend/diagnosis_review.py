"""Loopback-only abnormal diagnosis review support.

The review store is intentionally isolated from the normal assistant/database
configuration.  It requires explicit ``BF_DIAG_REVIEW_PG*`` variables and
refuses non-loopback PostgreSQL hosts.  A deployment may opt into a server-side
onsite identity so scoring does not require a browser login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from http.cookies import SimpleCookie
from typing import Any, Iterable, Mapping, Optional, Sequence


DIAGNOSIS_KEYS = (
    "normal",
    "lowline",
    "edge",
    "center",
    "channel",
    "cold",
    "hot",
    "column",
)
DIAGNOSIS_LABELS = {
    "normal": "正常顺行",
    "lowline": "低料线",
    "edge": "边缘煤气流发展",
    "center": "边缘不足/中心过吹",
    "channel": "管道行程",
    "cold": "热制度下行",
    "hot": "热制度上行",
    "column": "崩滑料/悬料",
}
VERDICTS = {"correct", "incorrect", "uncertain"}
SESSION_COOKIE = "bf_diag_review_session"
DEFAULT_ALLOWED_ROLES = ("高组长",)
DEFAULT_ANONYMOUS_USERNAME = "onsite_8093"
DEFAULT_ANONYMOUS_ROLE = "现场高炉长"
SIGNED_SESSION_IDENTITY = "signed_session"
ONSITE_ANONYMOUS_IDENTITY = "onsite_anonymous"
_EPHEMERAL_SESSION_SECRET = secrets.token_bytes(48)
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ReviewConfigurationError(RuntimeError):
    """Raised when the local review store is unsafe or incomplete."""


class ReviewValidationError(ValueError):
    """Raised when a review request does not satisfy the contract."""


@dataclass(frozen=True)
class ReviewConfig:
    enabled: bool
    test_mode: bool
    require_login: bool
    anonymous_username: str
    anonymous_role: str
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    pg_schema: str
    allowed_roles: tuple[str, ...]
    session_ttl_seconds: int

    @property
    def store_configured(self) -> bool:
        return all((self.pg_host, self.pg_database, self.pg_user, self.pg_password))


def env_truthy(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def review_enabled() -> bool:
    return env_truthy("BF_DIAGNOSIS_REVIEW_ENABLED", False)


def review_test_mode_enabled() -> bool:
    return env_truthy("BF_DIAGNOSIS_REVIEW_TEST_MODE", False)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_review_config(require_store: bool = False) -> ReviewConfig:
    host = os.getenv("BF_DIAG_REVIEW_PGHOST", "").strip()
    schema = os.getenv("BF_DIAG_REVIEW_PGSCHEMA", "bf_assistant").strip() or "bf_assistant"
    if not _SCHEMA_RE.fullmatch(schema):
        raise ReviewConfigurationError("BF_DIAG_REVIEW_PGSCHEMA 不是安全的 PostgreSQL schema 名称")
    try:
        port = int(os.getenv("BF_DIAG_REVIEW_PGPORT", "18000"))
        ttl = int(os.getenv("BF_AUTH_SESSION_TTL_SECONDS", "28800"))
    except ValueError as exc:
        raise ReviewConfigurationError("复核数据库端口或会话有效期不是整数") from exc
    roles = _split_csv(os.getenv("BF_DIAG_REVIEW_ALLOWED_ROLES", ",".join(DEFAULT_ALLOWED_ROLES)))
    password = os.getenv("BF_DIAG_REVIEW_PGPASSWORD", "")
    password_env = os.getenv("BF_DIAG_REVIEW_PGPASSWORD_ENV", "").strip()
    if not password and password_env:
        if not _ENV_NAME_RE.fullmatch(password_env):
            raise ReviewConfigurationError("BF_DIAG_REVIEW_PGPASSWORD_ENV 不是安全的环境变量名称")
        password = os.getenv(password_env, "")
    config = ReviewConfig(
        enabled=review_enabled(),
        test_mode=review_test_mode_enabled(),
        require_login=env_truthy("BF_DIAG_REVIEW_REQUIRE_LOGIN", True),
        anonymous_username=(
            os.getenv("BF_DIAG_REVIEW_ANONYMOUS_USERNAME", DEFAULT_ANONYMOUS_USERNAME).strip()
            or DEFAULT_ANONYMOUS_USERNAME
        ),
        anonymous_role=(
            os.getenv("BF_DIAG_REVIEW_ANONYMOUS_ROLE", DEFAULT_ANONYMOUS_ROLE).strip()
            or DEFAULT_ANONYMOUS_ROLE
        ),
        pg_host=host,
        pg_port=port,
        pg_database=os.getenv("BF_DIAG_REVIEW_PGDATABASE", "").strip(),
        pg_user=os.getenv("BF_DIAG_REVIEW_PGUSER", "").strip(),
        pg_password=password,
        pg_schema=schema,
        allowed_roles=roles or DEFAULT_ALLOWED_ROLES,
        session_ttl_seconds=max(60, ttl),
    )
    if require_store:
        if not config.store_configured:
            raise ReviewConfigurationError(
                "必须显式配置 BF_DIAG_REVIEW_PGHOST/PGDATABASE/PGUSER/PGPASSWORD"
            )
        if not is_loopback_host(config.pg_host):
            raise ReviewConfigurationError("复核数据库只允许使用本机回环地址")
    return config


def is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def client_is_loopback(client_address: Any) -> bool:
    host = client_address[0] if isinstance(client_address, (tuple, list)) else str(client_address or "")
    return is_loopback_host(host)


def role_is_allowed(role: str, config: Optional[ReviewConfig] = None) -> bool:
    cfg = config or load_review_config()
    return str(role or "").strip() in cfg.allowed_roles


def submission_identity(
    session: Optional[Mapping[str, Any]],
    config: Optional[ReviewConfig] = None,
) -> Optional[dict[str, str]]:
    """Return a server-controlled writer identity for one score submission.

    Browser payload fields are deliberately ignored.  An allowed signed session
    keeps its named identity; when login is disabled every other request uses the
    fixed onsite identity from server configuration.
    """
    cfg = config or load_review_config()
    if session and role_is_allowed(str(session.get("role") or ""), cfg):
        return {
            "sub": str(session.get("sub") or ""),
            "role": str(session.get("role") or ""),
            "identity_mode": SIGNED_SESSION_IDENTITY,
        }
    if cfg.require_login:
        return None
    return {
        "sub": cfg.anonymous_username,
        "role": cfg.anonymous_role,
        "identity_mode": ONSITE_ANONYMOUS_IDENTITY,
    }


def authenticate_account(accounts: Mapping[str, Mapping[str, str]], username: str, password: str) -> Optional[dict[str, str]]:
    account = accounts.get(str(username or "").strip())
    expected = str(account.get("password") or "") if account else ""
    if not account or not password or not hmac.compare_digest(str(password), expected):
        return None
    return {"username": str(username).strip(), "role": str(account.get("role") or "")}


def display_label(key: str) -> str:
    return DIAGNOSIS_LABELS.get(str(key or ""), str(key or "未知"))


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _session_secret() -> bytes:
    configured = os.getenv("BF_AUTH_SESSION_SECRET", "").encode("utf-8")
    return configured or _EPHEMERAL_SESSION_SECRET


def create_session_token(
    username: str,
    role: str,
    *,
    now: Optional[datetime] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
    issued = now or datetime.now(timezone.utc)
    ttl = ttl_seconds or load_review_config().session_ttl_seconds
    payload = {
        "sub": str(username),
        "role": str(role),
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl)).timestamp()),
        "nonce": secrets.token_hex(8),
    }
    encoded = _b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_session_token(token: str, *, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    try:
        encoded, supplied_signature = str(token or "").split(".", 1)
        expected_signature = _b64encode(
            hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
        current_ts = int((now or datetime.now(timezone.utc)).timestamp())
        if current_ts >= int(payload.get("exp", 0)):
            return None
        if not payload.get("sub") or not payload.get("role"):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def session_from_cookie(cookie_header: str) -> Optional[dict[str, Any]]:
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE)
    return verify_session_token(morsel.value) if morsel else None


def session_cookie_header(token: str, ttl_seconds: Optional[int] = None) -> str:
    ttl = ttl_seconds or load_review_config().session_ttl_seconds
    return (
        f"{SESSION_COOKIE}={token}; Path=/; Max-Age={int(ttl)}; "
        "HttpOnly; SameSite=Strict"
    )


def clear_session_cookie_header() -> str:
    return f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


def normalize_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def iso_timestamp(value: Any) -> str:
    return normalize_timestamp(value).isoformat()


def json_safe_value(value: Any) -> Any:
    """Normalize runtime database values before writing PostgreSQL JSONB."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def normalize_scores(raw_scores: Any) -> dict[str, float]:
    if isinstance(raw_scores, str):
        try:
            raw_scores = json.loads(raw_scores)
        except json.JSONDecodeError:
            raw_scores = {}
    raw = raw_scores if isinstance(raw_scores, Mapping) else {}
    normalized: dict[str, float] = {}
    for key in DIAGNOSIS_KEYS:
        try:
            normalized[key] = round(float(raw.get(key, 0.0)), 6)
        except (TypeError, ValueError):
            normalized[key] = 0.0
    return normalized


def scores_with_display_archive(canonical_context: Mapping[str, Any]) -> dict[str, Any]:
    """Keep legacy score keys and add a nested, backward-compatible display archive."""

    output: dict[str, Any] = normalize_scores(canonical_context.get("raw_scores"))
    if canonical_context.get("score_contract_version"):
        output["_display_contract"] = {
            "score_contract_version": canonical_context.get("score_contract_version"),
            "display_scores": canonical_context.get("display_scores") or {},
            "display_main_score": canonical_context.get("display_main_score"),
            "score_sources": canonical_context.get("score_sources") or {},
            "legacy_score_archive": canonical_context.get("legacy_score_archive") or {},
        }
    return output


def review_evidence_with_score_archive(canonical_context: Mapping[str, Any]) -> list[Any]:
    """Append score-source metadata without changing the review-event table schema."""

    evidence = list(canonical_context.get("evidence") or [])
    if canonical_context.get("score_sources") or canonical_context.get("legacy_score_archive"):
        evidence.append(
            {
                "type": "score_source_archive",
                "score_contract_version": canonical_context.get("score_contract_version"),
                "score_sources": canonical_context.get("score_sources") or {},
                "legacy_score_archive": canonical_context.get("legacy_score_archive") or {},
            }
        )
    return evidence


def abc_public_bundle_for_display(
    bundle: Mapping[str, Any],
    evaluation_ts: Any,
    *,
    now: datetime | None = None,
    max_wall_clock_age_minutes: int = 20,
) -> dict[str, Any]:
    """Fail a public ABC33 bundle closed when its latest batch is stale."""

    result = dict(bundle)
    try:
        evaluated = normalize_timestamp(evaluation_ts)
        wall_clock = normalize_timestamp(now or datetime.now(timezone.utc))
        age_seconds: float | None = (wall_clock - evaluated).total_seconds()
    except (TypeError, ValueError):
        age_seconds = None
    current = (
        age_seconds is not None
        and -60.0 <= age_seconds <= float(max_wall_clock_age_minutes * 60)
    )
    result["evaluation_age_seconds"] = (
        round(age_seconds, 3) if age_seconds is not None else None
    )
    result["batch_state"] = "current" if current else "stale"
    if current:
        return result
    stale_rules = []
    for item in result.get("rules") or []:
        rule = dict(item)
        rule.update({"score": None, "score_available": False, "status": "needs_data", "source_state": "stale_batch"})
        stale_rules.append(rule)
    result["rules"] = stale_rules
    result["alerts"] = []
    result["state"] = "needs_data"
    return result


def normalize_sequence(value: Any) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _episode_key(furnace_id: str, label: str, start_ts: datetime) -> str:
    material = f"{furnace_id}|{label}|{start_ts.isoformat()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]


def derive_current_episode(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    furnace_id: str = "BF",
    max_gap_minutes: int = 10,
) -> dict[str, Any]:
    rows = []
    for source in snapshots:
        try:
            item = dict(source)
            item["diagnosis_ts"] = normalize_timestamp(item["diagnosis_ts"])
            rows.append(item)
        except (KeyError, ValueError, TypeError):
            continue
    rows.sort(key=lambda row: row["diagnosis_ts"])
    if not rows:
        return {"available": False, "is_abnormal": False, "reason": "暂无诊断快照"}

    current = rows[-1]
    label = str(current.get("main_label") or "normal")
    episode_start = current["diagnosis_ts"]
    if label != "normal":
        cursor = current["diagnosis_ts"]
        for previous in reversed(rows[:-1]):
            gap = cursor - previous["diagnosis_ts"]
            if previous.get("main_label") != label or gap > timedelta(minutes=max_gap_minutes):
                break
            episode_start = previous["diagnosis_ts"]
            cursor = previous["diagnosis_ts"]

    scores = normalize_scores(current.get("raw_scores"))
    try:
        main_score = float(current.get("main_score", scores.get(label, 0.0)))
    except (TypeError, ValueError):
        main_score = scores.get(label, 0.0)
    try:
        main_confidence = float(current.get("main_confidence", 0.0))
    except (TypeError, ValueError):
        main_confidence = 0.0
    try:
        snapshot_id: Any = int(current["id"])
    except (KeyError, TypeError, ValueError):
        snapshot_id = str(current.get("id") or iso_timestamp(current["diagnosis_ts"]))

    candidates = [
        {"key": key, "label": display_label(key), "score": score}
        for key, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
        if key != label
    ]
    return {
        "available": True,
        "is_abnormal": label != "normal",
        "furnace_id": furnace_id,
        "episode_key": _episode_key(furnace_id, label, episode_start),
        "episode_start_ts": episode_start.isoformat(),
        "snapshot_id": snapshot_id,
        "diagnosis_ts": current["diagnosis_ts"].isoformat(),
        "main_label": label,
        "main_display_label": display_label(label),
        "main_score": round(main_score, 6),
        "main_confidence": round(main_confidence, 6),
        "secondary": normalize_sequence(current.get("secondary")),
        "raw_scores": scores,
        "candidates": candidates,
        "evidence": normalize_sequence(current.get("evidence")),
        "feature_snapshot": (
            dict(current.get("feature_snapshot"))
            if isinstance(current.get("feature_snapshot"), Mapping)
            else {}
        ),
        "data_coverage": current.get("data_coverage") if isinstance(current.get("data_coverage"), Mapping) else {},
        "snapshot_source": "live_readonly",
    }


def apply_abc33_display_score(
    context: Mapping[str, Any],
    abc_snapshot: Mapping[str, Any] | None,
    *,
    diagnosis_key: str = "hot",
    rule_id: str = "B4",
    max_age_minutes: int = 15,
    max_wall_clock_age_minutes: int = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Use one ABC33 rule as the production display score for a legacy diagnosis key.

    The legacy eight-class score remains available in ``raw_scores`` for
    historical review and existing analysis contracts.  ``display_scores`` and
    the matching candidate/main display score fail closed when the ABC33 rule
    is unavailable, invalid, or outside the allowed timestamp window.
    """

    result = dict(context)
    raw_scores = dict(context.get("raw_scores") or {})
    display_scores: dict[str, float | None] = {
        key: raw_scores.get(key) for key in DIAGNOSIS_KEYS
    }
    legacy_score = raw_scores.get(diagnosis_key)
    source: dict[str, Any] = {
        "source": "abc33",
        "rule_id": rule_id,
        "available": False,
        "used_for_display": False,
        "fallback_used": False,
        "state": "needs_data",
    }
    canonical_score: float | None = None

    snapshot = dict(abc_snapshot or {})
    rule = snapshot.get("rule") if isinstance(snapshot.get("rule"), Mapping) else None
    if rule is not None:
        source.update({
            "evaluation_id": snapshot.get("evaluation_id"),
            "catalog_version": snapshot.get("catalog_version"),
            "config_version": snapshot.get("config_version"),
            "source_snapshot_id": snapshot.get("source_snapshot_id"),
            "source_snapshot_match": bool(snapshot.get("source_snapshot_match")),
            "status": rule.get("status"),
        })
        try:
            diagnosis_ts = normalize_timestamp(context.get("diagnosis_ts"))
            evaluation_ts = normalize_timestamp(snapshot.get("evaluation_ts"))
            source["evaluation_ts"] = evaluation_ts.isoformat()
            age_minutes = (diagnosis_ts - evaluation_ts).total_seconds() / 60.0
            source["age_minutes"] = round(age_minutes, 3)
            score = float(rule.get("score"))
            rule_identity_valid = str(rule.get("rule_id") or "") == rule_id
            score_in_range = 0.0 <= score <= 100.0
            versioned = bool(snapshot.get("catalog_version")) and bool(
                snapshot.get("config_version")
            )
            score_available = rule.get("score_available") is not False
            status_available = str(rule.get("status") or "") != "needs_data"
            wall_clock = normalize_timestamp(now or datetime.now(timezone.utc))
            wall_clock_age_minutes = (wall_clock - evaluation_ts).total_seconds() / 60.0
            source["wall_clock_age_minutes"] = round(wall_clock_age_minutes, 3)
            time_aligned = 0.0 <= age_minutes <= float(max_age_minutes)
            wall_clock_current = -1.0 <= wall_clock_age_minutes <= float(max_wall_clock_age_minutes)
            if (
                math.isfinite(score)
                and score_in_range
                and rule_identity_valid
                and versioned
                and score_available
                and status_available
                and time_aligned
                and wall_clock_current
            ):
                canonical_score = round(score, 6)
                source.update({"available": True, "used_for_display": True, "state": "current"})
            elif not time_aligned or not wall_clock_current:
                source["state"] = "stale"
            else:
                source["state"] = "invalid" if not (rule_identity_valid and score_in_range and versioned) else "needs_data"
        except (TypeError, ValueError):
            source["state"] = "invalid"
    elif snapshot.get("error_type"):
        source.update({"state": "unavailable", "error_type": str(snapshot["error_type"])})

    display_scores[diagnosis_key] = canonical_score
    candidates = []
    for item in context.get("candidates") or []:
        candidate = dict(item)
        if candidate.get("key") == diagnosis_key:
            candidate["score"] = canonical_score
            candidate["score_source"] = "abc33"
            candidate["rule_id"] = rule_id
        candidates.append(candidate)

    display_main_score: float | None = context.get("main_score")
    if context.get("main_label") == diagnosis_key:
        display_main_score = canonical_score

    result.update({
        "score_contract_version": "diagnosis-review-score-source.v2",
        "display_scores": display_scores,
        "display_main_score": display_main_score,
        "candidates": candidates,
        "score_sources": {diagnosis_key: source},
        "legacy_score_archive": {
            diagnosis_key: {
                "source": "legacy_diagnosis_raw_scores",
                "score": legacy_score,
                "archived": True,
                "used_for_display": False,
            }
        },
    })
    return result


_FIXTURE_SCORES = {
    "normal": {"normal": 92, "lowline": 8, "edge": 11, "center": 7, "channel": 10, "cold": 18, "hot": 12, "column": 4},
    "cold": {"normal": 34, "lowline": 31, "edge": 29, "center": 17, "channel": 24, "cold": 87, "hot": 8, "column": 18},
    "hot": {"normal": 27, "lowline": 12, "edge": 35, "center": 21, "channel": 30, "cold": 9, "hot": 84, "column": 16},
    "lowline": {"normal": 22, "lowline": 91, "edge": 44, "center": 26, "channel": 38, "cold": 30, "hot": 16, "column": 27},
    "channel": {"normal": 19, "lowline": 45, "edge": 62, "center": 41, "channel": 89, "cold": 23, "hot": 31, "column": 36},
}


def build_fixture_context(label: str, case_id: str = "default") -> dict[str, Any]:
    diagnosis_key = label if label in _FIXTURE_SCORES else "normal"
    identity = f"{diagnosis_key}:{case_id or 'default'}"
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    synthetic_id = -int.from_bytes(digest[:4], "big")
    synthetic_ts = datetime(2026, 8, 4, tzinfo=timezone(timedelta(hours=8))) + timedelta(
        seconds=int.from_bytes(digest[4:8], "big") % 86400
    )
    row = {
        "id": synthetic_id,
        "diagnosis_ts": synthetic_ts,
        "main_label": diagnosis_key,
        "main_score": _FIXTURE_SCORES[diagnosis_key][diagnosis_key],
        "main_confidence": 0.0,
        "secondary": [],
        "raw_scores": _FIXTURE_SCORES[diagnosis_key],
        "evidence": (
            [
                {"title": "low_body_temperature", "detail": "低于历史基线"},
                {"variable": "low_blast_pressure", "detail": "低于历史基线"},
                {"rule": "operation_heat_reduction", "detail": "操作记录已确认"},
                {"name": "future_unknown_code", "detail": "未知内部码应使用中文兜底"},
                {"title": "<img src=x onerror=alert(1)>", "detail": "转义检查"},
            ]
            if str(case_id).startswith("evidence-cn-")
            else [
                {"title": "本机测试证据", "detail": f"测试场景：{display_label(diagnosis_key)}"},
                {"title": "边界说明", "detail": "该场景仅用于交互验收，不代表真实生产诊断。"},
            ]
        ),
        "feature_snapshot": {
            "z30_T_top_slope": -0.62,
            "z60_T_body_lower": -1.08,
            "z_T_taphole_mean": -0.84,
            "z60_P_blast": -0.91,
            "z60_PI": 0.94,
            "z60_GasUtil": -0.73,
            "z60_T_blast": -0.58,
            "zstd_P_top": 0.42,
            "zstd_DP_total": 0.51,
            "zstd_PI": 0.38,
            "zstd_P_blast": 0.47,
            "DispTop_15": 0.21,
            "L_diff_NS": 0.12,
        },
        "data_coverage": {"available": 126, "expected": 133, "ratio": 126 / 133},
    }
    context = derive_current_episode([row], furnace_id="BF-local-fixture")
    context["episode_key"] = hashlib.sha256(f"fixture|{identity}".encode("utf-8")).hexdigest()[:32]
    context["snapshot_source"] = "local_fixture"
    context["fixture_label"] = diagnosis_key
    context["fixture_case_id"] = case_id or "default"
    return context


def validate_review_payload(payload: Any, canonical_context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ReviewValidationError("请求体必须是 JSON 对象")
    verdict = str(payload.get("verdict") or "").strip()
    if verdict not in VERDICTS:
        raise ReviewValidationError("复核结论必须是诊断正确、诊断不正确或暂无法判断")
    corrected_main = str(payload.get("corrected_main_label") or "").strip() or None
    corrected_secondary = str(payload.get("corrected_secondary_label") or "").strip() or None
    if verdict == "incorrect" and corrected_main not in DIAGNOSIS_KEYS:
        raise ReviewValidationError("诊断不正确时必须选择实际主炉况")
    if verdict != "incorrect" and (corrected_main or corrected_secondary):
        raise ReviewValidationError("只有诊断不正确时才能填写纠正炉况")
    if corrected_secondary and corrected_secondary not in DIAGNOSIS_KEYS:
        raise ReviewValidationError("纠正次炉况不在允许范围内")
    if corrected_main and corrected_secondary == corrected_main:
        raise ReviewValidationError("实际主炉况与次炉况不能相同")
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        raise ReviewValidationError("幂等键格式无效")
    if str(payload.get("episode_key") or "") != str(canonical_context.get("episode_key") or ""):
        raise ReviewValidationError("异常段已变化，请刷新后重新复核")
    if str(payload.get("snapshot_id") or "") != str(canonical_context.get("snapshot_id") or ""):
        raise ReviewValidationError("诊断快照已变化，请刷新后重新复核")
    note = str(payload.get("note") or "").strip()
    if len(note) > 2000:
        raise ReviewValidationError("备注不能超过2000个字符")
    human_match_score = optional_human_score(payload.get("human_match_score"))
    suggestion = str(payload.get("suggestion") or "").strip()
    if len(suggestion) > 2000:
        raise ReviewValidationError("建议不能超过2000个字符")
    return {
        "verdict": verdict,
        "corrected_main_label": corrected_main,
        "corrected_secondary_label": corrected_secondary,
        "note": note,
        "human_match_score": human_match_score,
        "suggestion": suggestion,
        "idempotency_key": idempotency_key,
        "source_page": str(payload.get("source_page") or "").strip()[:300],
    }


def optional_human_score(value: Any) -> Optional[int]:
    """Normalize an optional 0-100 integer score supplied by a furnace leader."""
    if value is None or str(value).strip() == "":
        return None
    try:
        score = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ReviewValidationError("高炉长人工匹配分必须是0到100的整数") from exc
    if score < 0 or score > 100:
        raise ReviewValidationError("高炉长人工匹配分必须在0到100之间")
    return score


def validate_manual_score_payload(payload: Any, canonical_context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a manual score/suggestion for one diagnosis label at one snapshot."""
    if not isinstance(payload, Mapping):
        raise ReviewValidationError("请求体必须是 JSON 对象")
    target_label = str(payload.get("target_label") or "").strip()
    if target_label not in DIAGNOSIS_KEYS:
        raise ReviewValidationError("请选择有效的炉况诊断项")
    if str(payload.get("snapshot_id") or "") != str(canonical_context.get("snapshot_id") or ""):
        raise ReviewValidationError("诊断快照已变化，请刷新后重新评分")
    human_match_score = optional_human_score(payload.get("human_match_score"))
    suggestion = str(payload.get("suggestion") or "").strip()
    if len(suggestion) > 2000:
        raise ReviewValidationError("建议不能超过2000个字符")
    if human_match_score is None and not suggestion:
        raise ReviewValidationError("请填写人工匹配分或建议；如不填写可直接关闭弹窗")
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        raise ReviewValidationError("幂等键格式无效")
    return {
        "target_label": target_label,
        "human_match_score": human_match_score,
        "suggestion": suggestion,
        "idempotency_key": idempotency_key,
        "source_page": str(payload.get("source_page") or "").strip()[:300],
    }


REVIEW_TABLE_DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE IF NOT EXISTS {schema}.diagnosis_review_events (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    furnace_id TEXT NOT NULL,
    episode_key TEXT NOT NULL,
    episode_start_ts TIMESTAMPTZ NOT NULL,
    diagnosis_snapshot_id TEXT NOT NULL,
    diagnosis_ts TIMESTAMPTZ NOT NULL,
    main_label TEXT NOT NULL,
    main_score DOUBLE PRECISION NOT NULL,
    main_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    secondary JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_scores JSONB NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_coverage JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    verdict TEXT NOT NULL CHECK (verdict IN ('correct', 'incorrect', 'uncertain')),
    corrected_main_label TEXT,
    corrected_secondary_label TEXT,
    note TEXT NOT NULL DEFAULT '',
    human_match_score SMALLINT CHECK (human_match_score BETWEEN 0 AND 100),
    suggestion TEXT NOT NULL DEFAULT '',
    reviewer_username TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    identity_mode TEXT NOT NULL DEFAULT 'signed_session',
    snapshot_source TEXT NOT NULL CHECK (snapshot_source IN ('live_readonly', 'local_fixture')),
    source_page TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS diagnosis_review_events_episode_idx
    ON {schema}.diagnosis_review_events (episode_key, created_at DESC);
CREATE INDEX IF NOT EXISTS diagnosis_review_events_reviewer_idx
    ON {schema}.diagnosis_review_events (reviewer_username, created_at DESC);
ALTER TABLE {schema}.diagnosis_review_events
    ADD COLUMN IF NOT EXISTS human_match_score SMALLINT CHECK (human_match_score BETWEEN 0 AND 100);
ALTER TABLE {schema}.diagnosis_review_events
    ADD COLUMN IF NOT EXISTS suggestion TEXT NOT NULL DEFAULT '';
ALTER TABLE {schema}.diagnosis_review_events
    ADD COLUMN IF NOT EXISTS identity_mode TEXT NOT NULL DEFAULT 'signed_session';

CREATE TABLE IF NOT EXISTS {schema}.diagnosis_manual_score_events (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    furnace_id TEXT NOT NULL,
    diagnosis_snapshot_id TEXT NOT NULL,
    diagnosis_ts TIMESTAMPTZ NOT NULL,
    target_label TEXT NOT NULL,
    system_main_label TEXT NOT NULL,
    system_main_score DOUBLE PRECISION NOT NULL,
    system_raw_scores JSONB NOT NULL,
    human_match_score SMALLINT CHECK (human_match_score BETWEEN 0 AND 100),
    suggestion TEXT NOT NULL DEFAULT '',
    reviewer_username TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    identity_mode TEXT NOT NULL DEFAULT 'signed_session',
    snapshot_source TEXT NOT NULL CHECK (snapshot_source IN ('live_readonly', 'local_fixture')),
    source_page TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (human_match_score IS NOT NULL OR length(btrim(suggestion)) > 0)
);
CREATE INDEX IF NOT EXISTS diagnosis_manual_score_snapshot_idx
    ON {schema}.diagnosis_manual_score_events (diagnosis_ts DESC, target_label, created_at DESC);
CREATE INDEX IF NOT EXISTS diagnosis_manual_score_reviewer_idx
    ON {schema}.diagnosis_manual_score_events (reviewer_username, created_at DESC);
ALTER TABLE {schema}.diagnosis_manual_score_events
    ADD COLUMN IF NOT EXISTS identity_mode TEXT NOT NULL DEFAULT 'signed_session';

CREATE TABLE IF NOT EXISTS {schema}.diagnosis_ai_analysis_snapshots (
    id BIGSERIAL PRIMARY KEY,
    furnace_id TEXT NOT NULL,
    diagnosis_snapshot_id TEXT NOT NULL,
    diagnosis_ts TIMESTAMPTZ NOT NULL,
    bucket_ts TIMESTAMPTZ NOT NULL,
    bucket_minutes SMALLINT NOT NULL DEFAULT 5 CHECK (bucket_minutes BETWEEN 1 AND 60),
    main_label TEXT NOT NULL,
    system_raw_scores JSONB NOT NULL,
    canonical_context JSONB NOT NULL,
    analyses JSONB NOT NULL DEFAULT '[]'::jsonb,
    generation_state TEXT NOT NULL CHECK (
        generation_state IN ('preparing', 'reasoning', 'completed', 'failed')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    model_public_name TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (furnace_id, bucket_ts, prompt_version)
);
CREATE INDEX IF NOT EXISTS diagnosis_ai_analysis_snapshot_idx
    ON {schema}.diagnosis_ai_analysis_snapshots (diagnosis_ts DESC, generation_state);
CREATE INDEX IF NOT EXISTS diagnosis_ai_analysis_bucket_idx
    ON {schema}.diagnosis_ai_analysis_snapshots (bucket_ts DESC, main_label);
"""


class DiagnosisReviewStore:
    """Append-only event store backed by explicitly configured local PostgreSQL."""

    def __init__(self, config: Optional[ReviewConfig] = None):
        self.config = config or load_review_config(require_store=True)
        if not self.config.store_configured or not is_loopback_host(self.config.pg_host):
            raise ReviewConfigurationError("复核事件存储未显式配置为本机 PostgreSQL")

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise ReviewConfigurationError("缺少 psycopg，无法连接本机复核数据库") from exc
        return psycopg.connect(
            host=self.config.pg_host,
            port=self.config.pg_port,
            dbname=self.config.pg_database,
            user=self.config.pg_user,
            password=self.config.pg_password,
            connect_timeout=5,
        )

    @property
    def table_name(self) -> str:
        return f"{self.config.pg_schema}.diagnosis_review_events"

    @property
    def manual_score_table_name(self) -> str:
        return f"{self.config.pg_schema}.diagnosis_manual_score_events"

    @property
    def ai_analysis_table_name(self) -> str:
        return f"{self.config.pg_schema}.diagnosis_ai_analysis_snapshots"

    def ensure_schema(self) -> None:
        ddl = REVIEW_TABLE_DDL.format(schema=self.config.pg_schema)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(ddl)

    def read_latest_diagnosis_rows(self, *, limit: int = 288) -> list[dict[str, Any]]:
        """Read canonical diagnosis snapshots through the isolated review connection."""
        safe_limit = max(1, min(int(limit), 2880))
        sql = """
            SELECT * FROM (
                SELECT DISTINCT ON (diagnosis_ts)
                       id, diagnosis_ts, main_label, main_score, main_confidence,
                       secondary_label, secondary_score, secondary_confidence,
                       evidence, raw_scores, feature_snapshot, data_coverage, updated_at
                FROM bf_sensor.diagnosis_snapshots
                ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
            ) snapshots
            ORDER BY diagnosis_ts DESC
            LIMIT %s
        """
        columns = (
            "id", "diagnosis_ts", "main_label", "main_score", "main_confidence",
            "secondary_label", "secondary_score", "secondary_confidence",
            "evidence", "raw_scores", "feature_snapshot", "data_coverage", "updated_at",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (safe_limit,))
                rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(zip(columns, row))
            item["secondary"] = []
            if item.get("secondary_label"):
                item["secondary"].append(
                    {
                        "label": item.get("secondary_label"),
                        "score": item.get("secondary_score"),
                        "confidence": item.get("secondary_confidence"),
                    }
                )
            result.append(item)
        return result

    def read_diagnosis_evidence_rows(
        self,
        *,
        diagnosis_ts: Any,
        variables: Sequence[str],
        window_minutes: int = 60,
        baseline_days: int = 30,
    ) -> dict[str, list[dict[str, Any]]]:
        """Read minute values and daily references used by score explanations.

        This is a read-only companion query.  It applies the same unaudited-zero
        boundary as the diagnosis scheduler and never writes or recalculates the
        canonical rule scores.
        """
        target = normalize_timestamp(diagnosis_ts)
        safe_variables = tuple(dict.fromkeys(str(item) for item in variables if item))
        if not safe_variables:
            return {"sensor_rows": [], "baseline_rows": []}
        start = target - timedelta(minutes=max(5, min(int(window_minutes), 180)))
        sensor_sql = """
            SELECT r.variable_name, v.ts,
                   CASE
                       WHEN v.value = 0
                        AND COALESCE(z.verification_status, '') <> 'verified_zero'
                       THEN NULL
                       ELSE v.value
                   END AS value
            FROM bf_sensor.one_minute_values v
            JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
            LEFT JOIN bf_sensor.zero_value_audits z
              ON z.tag_long_name = v.tag_long_name
             AND z.ts = v.ts
             AND z.pspace_aggregate = v.aggregate
            WHERE r.is_enabled = true
              AND r.is_derived = false
              AND r.variable_name = ANY(%s)
              AND v.ts >= %s
              AND v.ts <= %s
            ORDER BY r.variable_name, v.ts
        """
        baseline_sql = """
            SELECT DISTINCT ON (variable_name)
                   variable_name, baseline_day, median_ref, iqr_ref,
                   p10, p90, sample_count, coverage_ratio,
                   baseline_window_start, baseline_window_end
            FROM bf_sensor.daily_baselines
            WHERE baseline_days = %s
              AND baseline_day <= %s
              AND variable_name = ANY(%s)
            ORDER BY variable_name, baseline_day DESC, updated_at DESC
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sensor_sql, (list(safe_variables), start, target))
                sensor_values = cursor.fetchall()
                cursor.execute(
                    baseline_sql,
                    (int(baseline_days), target.date(), list(safe_variables)),
                )
                baseline_values = cursor.fetchall()
        sensor_columns = ("variable_name", "ts", "value")
        baseline_columns = (
            "variable_name", "baseline_day", "median_ref", "iqr_ref",
            "p10", "p90", "sample_count", "coverage_ratio",
            "baseline_window_start", "baseline_window_end",
        )
        return {
            "sensor_rows": [dict(zip(sensor_columns, row)) for row in sensor_values],
            "baseline_rows": [dict(zip(baseline_columns, row)) for row in baseline_values],
        }

    def get_ai_analysis(
        self,
        *,
        furnace_id: str,
        bucket_ts: Any,
        prompt_version: str,
    ) -> Optional[dict[str, Any]]:
        """Return the durable analysis state for one five-minute bucket."""
        sql = f"""
            SELECT id, furnace_id, diagnosis_snapshot_id, diagnosis_ts, bucket_ts,
                   bucket_minutes, main_label, system_raw_scores, canonical_context,
                   analyses, generation_state, attempt_count, last_error_code,
                   prompt_version, snapshot_hash, model_public_name, started_at,
                   completed_at, created_at, updated_at
            FROM {self.ai_analysis_table_name}
            WHERE furnace_id = %s AND bucket_ts = %s AND prompt_version = %s
            LIMIT 1
        """
        columns = (
            "id", "furnace_id", "diagnosis_snapshot_id", "diagnosis_ts", "bucket_ts",
            "bucket_minutes", "main_label", "system_raw_scores", "canonical_context",
            "analyses", "generation_state", "attempt_count", "last_error_code",
            "prompt_version", "snapshot_hash", "model_public_name", "started_at",
            "completed_at", "created_at", "updated_at",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        furnace_id,
                        normalize_timestamp(bucket_ts),
                        prompt_version,
                    ),
                )
                row = cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    def begin_ai_analysis(
        self,
        context: Mapping[str, Any],
        *,
        prompt_version: str,
        snapshot_hash: str,
        model_public_name: str,
    ) -> dict[str, Any]:
        """Create or mark one derived five-minute analysis row as reasoning."""
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise ReviewConfigurationError("缺少 psycopg JSON 支持") from exc
        sql = f"""
            INSERT INTO {self.ai_analysis_table_name} AS current_row (
                furnace_id, diagnosis_snapshot_id, diagnosis_ts, bucket_ts,
                bucket_minutes, main_label, system_raw_scores, canonical_context,
                generation_state, attempt_count, prompt_version, snapshot_hash,
                model_public_name, started_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                'reasoning', 1, %s, %s, %s, NOW(), NOW()
            )
            ON CONFLICT (furnace_id, bucket_ts, prompt_version) DO UPDATE SET
                diagnosis_snapshot_id = EXCLUDED.diagnosis_snapshot_id,
                diagnosis_ts = EXCLUDED.diagnosis_ts,
                main_label = EXCLUDED.main_label,
                system_raw_scores = EXCLUDED.system_raw_scores,
                canonical_context = EXCLUDED.canonical_context,
                generation_state = 'reasoning',
                attempt_count = current_row.attempt_count + 1,
                last_error_code = '',
                snapshot_hash = EXCLUDED.snapshot_hash,
                model_public_name = EXCLUDED.model_public_name,
                started_at = NOW(),
                completed_at = NULL,
                updated_at = NOW()
            RETURNING id, generation_state, attempt_count, started_at, updated_at
        """
        values = (
            str(context.get("furnace_id") or "BF"),
            str(context.get("snapshot_id") or ""),
            normalize_timestamp(context["diagnosis_ts"]),
            normalize_timestamp(context["bucket_ts"]),
            int(context.get("bucket_minutes") or 5),
            str(context.get("main_label") or "normal"),
            Jsonb(json_safe_value(normalize_scores(context.get("scores")))),
            Jsonb(json_safe_value(dict(context))),
            prompt_version,
            snapshot_hash,
            model_public_name,
        )
        columns = ("id", "generation_state", "attempt_count", "started_at", "updated_at")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                row = cursor.fetchone()
        return dict(zip(columns, row))

    def complete_ai_analysis(
        self,
        *,
        furnace_id: str,
        bucket_ts: Any,
        prompt_version: str,
        snapshot_hash: str,
        analyses: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Persist a complete eight-condition result for the current bucket."""
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise ReviewConfigurationError("缺少 psycopg JSON 支持") from exc
        sql = f"""
            UPDATE {self.ai_analysis_table_name}
            SET analyses = %s,
                generation_state = 'completed',
                last_error_code = '',
                snapshot_hash = %s,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE furnace_id = %s AND bucket_ts = %s AND prompt_version = %s
            RETURNING id, generation_state, attempt_count, completed_at, updated_at
        """
        columns = ("id", "generation_state", "attempt_count", "completed_at", "updated_at")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        Jsonb(json_safe_value([dict(item) for item in analyses])),
                        snapshot_hash,
                        furnace_id,
                        normalize_timestamp(bucket_ts),
                        prompt_version,
                    ),
                )
                row = cursor.fetchone()
        if not row:
            raise ReviewConfigurationError("5分钟智能分析状态不存在，无法保存结果")
        return dict(zip(columns, row))

    def fail_ai_analysis(
        self,
        *,
        furnace_id: str,
        bucket_ts: Any,
        prompt_version: str,
        error_code: str,
    ) -> None:
        """Record a sanitized failure code without storing model output or secrets."""
        sql = f"""
            UPDATE {self.ai_analysis_table_name}
            SET generation_state = 'failed',
                last_error_code = %s,
                updated_at = NOW()
            WHERE furnace_id = %s AND bucket_ts = %s AND prompt_version = %s
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        str(error_code or "AnalysisError")[:120],
                        furnace_id,
                        normalize_timestamp(bucket_ts),
                        prompt_version,
                    ),
                )

    def insert_event(
        self,
        canonical_context: Mapping[str, Any],
        review: Mapping[str, Any],
        identity: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise ReviewConfigurationError("缺少 psycopg JSON 支持") from exc
        values = (
            review["idempotency_key"],
            str(canonical_context.get("furnace_id") or "BF"),
            str(canonical_context["episode_key"]),
            normalize_timestamp(canonical_context["episode_start_ts"]),
            str(canonical_context["snapshot_id"]),
            normalize_timestamp(canonical_context["diagnosis_ts"]),
            str(canonical_context["main_label"]),
            float(canonical_context.get("main_score", 0.0)),
            float(canonical_context.get("main_confidence", 0.0)),
            Jsonb(json_safe_value(canonical_context.get("secondary") or [])),
            Jsonb(json_safe_value(scores_with_display_archive(canonical_context))),
            Jsonb(json_safe_value(review_evidence_with_score_archive(canonical_context))),
            Jsonb(json_safe_value(canonical_context.get("data_coverage") or {})),
            review["verdict"],
            review.get("corrected_main_label"),
            review.get("corrected_secondary_label"),
            review.get("note") or "",
            review.get("human_match_score"),
            review.get("suggestion") or "",
            str(identity.get("sub") or ""),
            str(identity.get("role") or ""),
            str(identity.get("identity_mode") or SIGNED_SESSION_IDENTITY),
            str(canonical_context.get("snapshot_source") or "live_readonly"),
            review.get("source_page") or "",
        )
        insert_sql = f"""
            INSERT INTO {self.table_name} (
                idempotency_key, furnace_id, episode_key, episode_start_ts,
                diagnosis_snapshot_id, diagnosis_ts, main_label, main_score,
                main_confidence, secondary, raw_scores, evidence, data_coverage,
                verdict, corrected_main_label, corrected_secondary_label, note,
                human_match_score, suggestion,
                reviewer_username, reviewer_role, identity_mode, snapshot_source, source_page
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, idempotency_key, episode_key, diagnosis_snapshot_id,
                      verdict, human_match_score, suggestion, reviewer_username,
                      reviewer_role, identity_mode, snapshot_source, created_at
        """
        lookup_sql = f"""
            SELECT id, idempotency_key, episode_key, diagnosis_snapshot_id,
                   verdict, human_match_score, suggestion, reviewer_username,
                   reviewer_role, identity_mode, snapshot_source, created_at
            FROM {self.table_name}
            WHERE idempotency_key = %s
        """
        columns = (
            "id", "idempotency_key", "episode_key", "diagnosis_snapshot_id",
            "verdict", "human_match_score", "suggestion", "reviewer_username",
            "reviewer_role", "identity_mode", "snapshot_source", "created_at",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(insert_sql, values)
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(lookup_sql, (review["idempotency_key"],))
                    row = cursor.fetchone()
        return dict(zip(columns, row)), created

    def list_events(
        self,
        *,
        episode_key: str = "",
        reviewer_username: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if episode_key:
            conditions.append("episode_key = %s")
            params.append(episode_key)
        if reviewer_username:
            conditions.append("reviewer_username = %s")
            params.append(reviewer_username)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        safe_limit = max(1, min(int(limit), 200))
        sql = f"""
            SELECT id, idempotency_key, furnace_id, episode_key, episode_start_ts,
                   diagnosis_snapshot_id, diagnosis_ts, main_label, main_score,
                   main_confidence, secondary, raw_scores, evidence, data_coverage,
                   verdict, corrected_main_label, corrected_secondary_label, note,
                   human_match_score, suggestion,
                   reviewer_username, reviewer_role, identity_mode, snapshot_source,
                   source_page, created_at
            FROM {self.table_name}{where}
            ORDER BY created_at DESC
            LIMIT {safe_limit}
        """
        columns = (
            "id", "idempotency_key", "furnace_id", "episode_key", "episode_start_ts",
            "diagnosis_snapshot_id", "diagnosis_ts", "main_label", "main_score",
            "main_confidence", "secondary", "raw_scores", "evidence", "data_coverage",
            "verdict", "corrected_main_label", "corrected_secondary_label", "note",
            "human_match_score", "suggestion",
            "reviewer_username", "reviewer_role", "identity_mode", "snapshot_source",
            "source_page", "created_at",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def insert_manual_score_event(
        self,
        canonical_context: Mapping[str, Any],
        manual_score: Mapping[str, Any],
        identity: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Append one score/suggestion for a diagnosis label and snapshot."""
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise ReviewConfigurationError("缺少 psycopg JSON 支持") from exc
        values = (
            manual_score["idempotency_key"],
            str(canonical_context.get("furnace_id") or "BF"),
            str(canonical_context["snapshot_id"]),
            normalize_timestamp(canonical_context["diagnosis_ts"]),
            manual_score["target_label"],
            str(canonical_context["main_label"]),
            float(canonical_context.get("main_score", 0.0)),
            Jsonb(json_safe_value(scores_with_display_archive(canonical_context))),
            manual_score.get("human_match_score"),
            manual_score.get("suggestion") or "",
            str(identity.get("sub") or ""),
            str(identity.get("role") or ""),
            str(identity.get("identity_mode") or SIGNED_SESSION_IDENTITY),
            str(canonical_context.get("snapshot_source") or "live_readonly"),
            manual_score.get("source_page") or "",
        )
        insert_sql = f"""
            INSERT INTO {self.manual_score_table_name} (
                idempotency_key, furnace_id, diagnosis_snapshot_id, diagnosis_ts,
                target_label, system_main_label, system_main_score, system_raw_scores,
                human_match_score, suggestion, reviewer_username, reviewer_role,
                identity_mode, snapshot_source, source_page
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, idempotency_key, diagnosis_snapshot_id, diagnosis_ts,
                      target_label, human_match_score, suggestion, reviewer_username,
                      reviewer_role, identity_mode, snapshot_source, created_at
        """
        lookup_sql = f"""
            SELECT id, idempotency_key, diagnosis_snapshot_id, diagnosis_ts,
                   target_label, human_match_score, suggestion, reviewer_username,
                   reviewer_role, identity_mode, snapshot_source, created_at
            FROM {self.manual_score_table_name}
            WHERE idempotency_key = %s
        """
        columns = (
            "id", "idempotency_key", "diagnosis_snapshot_id", "diagnosis_ts",
            "target_label", "human_match_score", "suggestion", "reviewer_username",
            "reviewer_role", "identity_mode", "snapshot_source", "created_at",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(insert_sql, values)
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(lookup_sql, (manual_score["idempotency_key"],))
                    row = cursor.fetchone()
        return dict(zip(columns, row)), created

    def list_human_score_events(
        self,
        *,
        start: Any = None,
        end: Any = None,
        labels: Sequence[str] = (),
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Return manual and popup-origin score/suggestion events for dashboard joins."""
        conditions: list[str] = []
        params: list[Any] = []
        if start:
            conditions.append("diagnosis_ts >= %s")
            params.append(normalize_timestamp(start))
        if end:
            conditions.append("diagnosis_ts <= %s")
            params.append(normalize_timestamp(end))
        clean_labels = [label for label in labels if label in DIAGNOSIS_KEYS]
        if clean_labels:
            conditions.append("target_label = ANY(%s)")
            params.append(clean_labels)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        safe_limit = max(1, min(int(limit), 100000))
        sql = f"""
            WITH human_events AS (
                SELECT id, idempotency_key, diagnosis_snapshot_id, diagnosis_ts,
                       target_label, system_main_label, system_main_score,
                       system_raw_scores, human_match_score, suggestion,
                       reviewer_username, reviewer_role, snapshot_source,
                       source_page, created_at, 'manual_diagnosis'::text AS review_mode
                FROM {self.manual_score_table_name}
                UNION ALL
                SELECT id, idempotency_key, diagnosis_snapshot_id, diagnosis_ts,
                       main_label AS target_label, main_label AS system_main_label,
                       main_score AS system_main_score, raw_scores AS system_raw_scores,
                       human_match_score, suggestion, reviewer_username, reviewer_role,
                       snapshot_source, source_page, created_at,
                       'abnormal_popup'::text AS review_mode
                FROM {self.table_name}
                WHERE human_match_score IS NOT NULL OR length(btrim(suggestion)) > 0
            )
            SELECT * FROM human_events{where}
            ORDER BY diagnosis_ts DESC, created_at DESC
            LIMIT {safe_limit}
        """
        columns = (
            "id", "idempotency_key", "diagnosis_snapshot_id", "diagnosis_ts",
            "target_label", "system_main_label", "system_main_score", "system_raw_scores",
            "human_match_score", "suggestion", "reviewer_username", "reviewer_role",
            "snapshot_source", "source_page", "created_at", "review_mode",
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
