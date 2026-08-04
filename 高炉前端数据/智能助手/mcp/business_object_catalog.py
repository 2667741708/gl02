"""Unified business-object catalog for blast-furnace MCP services.

Static catalog files describe non-sensor business objects and sensor defaults.
Runtime sensor mappings are converted to the same contract so callers can
discover every supported object through one read-only interface.

Requirement: REQ-MCP-BUSINESS-OBJECT-CATALOG-20260726
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
MANIFEST_PATH = CATALOG_DIR / "catalog_manifest.json"
REQUIRED_FIELDS = (
    "object_id",
    "object_type",
    "display_name",
    "aliases",
    "capabilities",
    "status",
    "executor",
)
ALLOWED_STATUS = {"enabled", "disabled", "unavailable", "planned"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def normalize_search_text(value: Any) -> str:
    return re.sub(r"[\s,，。；;：:、_\-—（）()\[\]【】]+", "", str(value or "").lower())


def validate_business_object(item: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one object without requiring a third-party schema library."""

    missing = [field for field in REQUIRED_FIELDS if field not in item]
    if missing:
        raise ValueError(f"业务对象缺少字段 {missing}: {item.get('object_id')}")
    object_id = str(item.get("object_id") or "").strip()
    display_name = str(item.get("display_name") or "").strip()
    if not object_id or not display_name:
        raise ValueError("object_id/display_name不能为空")
    status = str(item.get("status") or "")
    if status not in ALLOWED_STATUS:
        raise ValueError(f"不支持的status={status}: {object_id}")
    aliases = [str(value).strip() for value in item.get("aliases") or [] if str(value).strip()]
    capabilities = [str(value).strip() for value in item.get("capabilities") or [] if str(value).strip()]
    executor = item.get("executor")
    if not isinstance(executor, dict) or not executor.get("service") or not isinstance(executor.get("tools"), list):
        raise ValueError(f"executor必须包含service和tools: {object_id}")
    normalized = dict(item)
    normalized["object_id"] = object_id
    normalized["display_name"] = display_name
    normalized["aliases"] = list(dict.fromkeys(aliases))
    normalized["capabilities"] = list(dict.fromkeys(capabilities))
    normalized["status"] = status
    normalized["unit"] = item.get("unit")
    normalized["executor"] = {
        **executor,
        "service": str(executor["service"]),
        "tools": list(dict.fromkeys(str(value) for value in executor["tools"] if str(value))),
    }
    normalized.setdefault("description", "")
    normalized.setdefault("metadata", {})
    return normalized


def sensor_display_name(variable: dict[str, Any]) -> str:
    description = str(variable.get("description") or "").strip()
    if description:
        description = re.sub(r"^2号炉", "", description).lstrip("_- ")
        return description
    return str(variable.get("variable_name") or "")


def sensor_status(variable: dict[str, Any]) -> str:
    source_status = str(variable.get("status") or "").lower()
    if source_status in {"missing", "disabled"}:
        return "disabled"
    if not (variable.get("tag_long_name") or variable.get("point_id")):
        return "unavailable"
    return "enabled"


def sensor_capabilities(variable: dict[str, Any], defaults: list[str]) -> list[str]:
    if sensor_status(variable) != "enabled":
        return ["metadata"]
    capabilities = list(defaults)
    if str(variable.get("variable_name") or "").startswith("T_body_L"):
        capabilities.append("matrix")
    return list(dict.fromkeys(capabilities))


def sensor_object(
    variable: dict[str, Any],
    defaults: dict[str, Any],
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variable_name = str(variable.get("variable_name") or "").strip()
    base = {
        "object_id": variable_name,
        "object_type": "sensor",
        "display_name": sensor_display_name(variable),
        "aliases": list(variable.get("aliases") or []),
        "unit": variable.get("unit") or None,
        "capabilities": sensor_capabilities(variable, list(defaults.get("capabilities") or [])),
        "status": sensor_status(variable),
        "description": str(variable.get("description") or ""),
        "executor": dict(defaults.get("executor") or {}),
        "metadata": {
            "variable_name": variable_name,
            "short_name": variable.get("short_name") or "",
            "point_id": variable.get("point_id") or variable.get("tag_long_name") or "",
            "source_branch": variable.get("source_branch") or "",
            "confidence": variable.get("confidence") or "",
        },
    }
    if override:
        for key, value in override.items():
            if key == "metadata":
                base["metadata"] = {**base["metadata"], **(value or {})}
            else:
                base[key] = value
    return validate_business_object(base)


def load_business_object_catalog(sensor_variables: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Load every catalog file and merge runtime sensor variables by object_id."""

    manifest = load_json(MANIFEST_PATH)
    sensor_config = load_json(CATALOG_DIR / "sensors.json")
    defaults = sensor_config.get("defaults") or {}
    overrides = {
        str(item.get("object_id") or ""): item
        for item in sensor_config.get("objects") or []
        if item.get("object_id")
    }
    objects: list[dict[str, Any]] = []
    positions: dict[str, int] = {}

    def add(item: dict[str, Any]) -> None:
        normalized = validate_business_object(item)
        object_id = normalized["object_id"]
        if object_id in positions:
            objects[positions[object_id]] = normalized
        else:
            positions[object_id] = len(objects)
            objects.append(normalized)

    for variable in sensor_variables:
        if variable.get("variable_name"):
            add(sensor_object(variable, defaults, overrides.get(str(variable["variable_name"]))))
    for object_id, override in overrides.items():
        if object_id not in positions:
            add(validate_business_object(override))
    for filename in manifest.get("files") or []:
        if filename == "sensors.json":
            continue
        payload = load_json(CATALOG_DIR / filename)
        for item in payload.get("objects") or []:
            add(item)

    counts: dict[str, int] = {}
    for item in objects:
        counts[item["object_type"]] = counts.get(item["object_type"], 0) + 1
    return {
        "catalog_version": manifest.get("catalog_version", "1.0.0"),
        "contract": manifest.get("contract", "business_object.schema.json"),
        "count": len(objects),
        "counts_by_type": counts,
        "objects": objects,
    }


def list_catalog_objects(
    catalog: dict[str, Any],
    object_type: str = "",
    capability: str = "",
    status: str = "enabled",
    limit: int = 200,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 200), 1000))
    items = []
    for item in catalog.get("objects") or []:
        if object_type and item.get("object_type") != object_type:
            continue
        if capability and capability not in (item.get("capabilities") or []):
            continue
        if status and item.get("status") != status:
            continue
        items.append(item)
    return items[:limit]


def search_catalog_objects(
    catalog: dict[str, Any],
    query: str,
    object_types: list[str] | None = None,
    capability: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    needle = normalize_search_text(query)
    if not needle:
        return []
    type_filter = {str(value) for value in object_types or [] if str(value)}
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for item in catalog.get("objects") or []:
        if type_filter and item.get("object_type") not in type_filter:
            continue
        if capability and capability not in (item.get("capabilities") or []):
            continue
        fields = [
            item.get("object_id"),
            item.get("display_name"),
            item.get("description"),
            *(item.get("aliases") or []),
        ]
        normalized_fields = [normalize_search_text(value) for value in fields if value]
        score = 0
        for field in normalized_fields:
            if needle == field:
                score = max(score, 100)
            elif needle in field:
                score = max(score, 80)
            elif field and field in needle:
                score = max(score, 60)
        if score:
            scored.append((score, str(item.get("object_id")), item))
    scored.sort(key=lambda value: (-value[0], value[1]))
    return [item for _, _, item in scored[: max(1, min(int(limit or 20), 100))]]


def get_catalog_object(catalog: dict[str, Any], object_id: str) -> dict[str, Any] | None:
    target = str(object_id or "").strip().lower()
    for item in catalog.get("objects") or []:
        if str(item.get("object_id") or "").lower() == target:
            return item
    return None
