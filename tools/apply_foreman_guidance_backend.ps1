$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Save-Utf8([string]$Path, [string]$Text) { [System.IO.File]::WriteAllText($Path, $Text, $utf8) }

$ddlPath = Join-Path $root "自动诊断服务\recommendation_audit_schema.sql"
$ddl = [System.IO.File]::ReadAllText($ddlPath, [Text.Encoding]::UTF8)
$ddlMarker = "CREATE OR REPLACE FUNCTION bf_assistant.reject_recommendation_audit_mutation()"
$ddlInsert = @'
CREATE TABLE IF NOT EXISTS bf_assistant.foreman_operational_guidance (
    id bigserial PRIMARY KEY,
    furnace_id text NOT NULL DEFAULT 'GL02',
    diagnosis_snapshot_id bigint,
    diagnosis_ts timestamptz NOT NULL,
    diagnosis_main_label text,
    diagnosis_score double precision,
    cold_pressure_computed_target double precision,
    cold_pressure_guidance_target double precision NOT NULL CHECK (cold_pressure_guidance_target >= 400),
    cold_pressure_effective_at timestamptz,
    pci_computed_target double precision,
    pci_guidance_target double precision NOT NULL CHECK (pci_guidance_target >= 0 AND pci_guidance_target <= 45),
    pci_effective_at timestamptz,
    pressure_limit_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pressure_limit_snapshot) = 'object'),
    pci_limit_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pci_limit_snapshot) = 'object'),
    pressure_source text NOT NULL CHECK (pressure_source IN ('foreman_manual', 'computed_fallback')),
    pci_source text NOT NULL CHECK (pci_source IN ('foreman_manual', 'computed_fallback')),
    approval_status text NOT NULL CHECK (approval_status IN ('confirmed', 'rejected')),
    entered_by text NOT NULL DEFAULT '值班工长',
    operator_note text NOT NULL DEFAULT '',
    request_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(request_payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_foreman_guidance_latest
    ON bf_assistant.foreman_operational_guidance (furnace_id, diagnosis_ts DESC, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_foreman_guidance_effective
    ON bf_assistant.foreman_operational_guidance (furnace_id, cold_pressure_effective_at DESC, pci_effective_at DESC);

'@
if ($ddl.IndexOf("bf_assistant.foreman_operational_guidance", [StringComparison]::Ordinal) -lt 0) { $ddl = $ddl.Replace($ddlMarker, $ddlInsert + $ddlMarker) }
$triggerMarker = "CREATE OR REPLACE VIEW bf_assistant.recommendation_audit_action_detail AS"
$triggerInsert = @'
DROP TRIGGER IF EXISTS trg_foreman_operational_guidance_immutable
    ON bf_assistant.foreman_operational_guidance;
CREATE TRIGGER trg_foreman_operational_guidance_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON bf_assistant.foreman_operational_guidance
FOR EACH STATEMENT EXECUTE FUNCTION bf_assistant.reject_recommendation_audit_mutation();

'@
if ($ddl.IndexOf("trg_foreman_operational_guidance_immutable", [StringComparison]::Ordinal) -lt 0) { $ddl = $ddl.Replace($triggerMarker, $triggerInsert + $triggerMarker) }
$commentText = "COMMENT ON COLUMN bf_assistant.recommendation_audit_actions.read_only IS" + [Environment]::NewLine + "    'True means the record is advice only and is not a process-control command.';"
$commentExtra = @'
COMMENT ON TABLE bf_assistant.foreman_operational_guidance IS
    'Append-only foreman guidance for cold-blast pressure and PCI setpoint; stored for audit only and never sent to equipment.';
COMMENT ON COLUMN bf_assistant.foreman_operational_guidance.pressure_source IS
    'foreman_manual when entered by the operator; computed_fallback when the current computed pressure is retained.';
'@
if ($ddl.IndexOf("COMMENT ON TABLE bf_assistant.foreman_operational_guidance", [StringComparison]::Ordinal) -lt 0) { $ddl = $ddl.Replace($commentText, $commentText + [Environment]::NewLine + $commentExtra.TrimEnd()) }
$versionMarker = "INSERT INTO bf_assistant.recommendation_audit_schema_versions (version, description)" + [Environment]::NewLine + "VALUES ('recommendation_audit.v2', 'Materialised cold-blast pressure and PCI setpoint control fields')" + [Environment]::NewLine + "ON CONFLICT (version) DO NOTHING;"
$versionExtra = $versionMarker + [Environment]::NewLine + [Environment]::NewLine + "INSERT INTO bf_assistant.recommendation_audit_schema_versions (version, description)" + [Environment]::NewLine + "VALUES ('recommendation_audit.v3', 'Append-only foreman operational guidance for pressure and PCI values')" + [Environment]::NewLine + "ON CONFLICT (version) DO NOTHING;"
if ($ddl.IndexOf("recommendation_audit.v3", [StringComparison]::Ordinal) -lt 0) { $ddl = $ddl.Replace($versionMarker, $versionExtra) }
Save-Utf8 $ddlPath $ddl

$storePath = Join-Path $root "自动诊断服务\recommendation_audit_store.py"
$store = [System.IO.File]::ReadAllText($storePath, [Text.Encoding]::UTF8)
$store = $store.Replace('AUDIT_ACTION_TABLE = "bf_assistant.recommendation_audit_actions"', 'AUDIT_ACTION_TABLE = "bf_assistant.recommendation_audit_actions"' + [Environment]::NewLine + 'GUIDANCE_TABLE = "bf_assistant.foreman_operational_guidance"' + [Environment]::NewLine + 'GUIDANCE_VARIABLES = {"P_blast_cold", "PCI_set"}')
$storeMarker = "def persist_recommendation_bundle("
$storeInsert = @'
def _guidance_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_foreman_guidance_request(request: Mapping[str, Any]) -> dict[str, Any]:
    body = _mapping(request)
    current = _mapping(body.get("current"))
    computed = _mapping(body.get("computed"))
    guidance = _mapping(body.get("guidance"))
    limits = _mapping(body.get("limits"))
    pressure_limits = _mapping(limits.get("P_blast_cold"))
    pci_limits = _mapping(limits.get("PCI_set"))
    current_pressure = _guidance_number(current.get("P_blast_cold"))
    current_pci = _guidance_number(current.get("PCI_set"))
    computed_pressure = _guidance_number(computed.get("P_blast_cold")) or current_pressure
    computed_pci = _guidance_number(computed.get("PCI_set")) or current_pci
    pressure_target = _guidance_number(guidance.get("P_blast_cold"))
    pci_target = _guidance_number(guidance.get("PCI_set"))
    pressure_source = "foreman_manual" if pressure_target is not None else "computed_fallback"
    pci_source = "foreman_manual" if pci_target is not None else "computed_fallback"
    pressure_target = pressure_target if pressure_target is not None else computed_pressure
    pci_target = pci_target if pci_target is not None else computed_pci
    diagnosis_ts = str(body.get("diagnosis_ts") or "").strip()
    if not diagnosis_ts:
        raise RecommendationAuditValidationError("diagnosis_ts is required for foreman guidance")
    if pressure_target is None:
        raise RecommendationAuditValidationError("P_blast_cold has no manual or computed fallback value")
    if pci_target is None:
        raise RecommendationAuditValidationError("PCI_set has no manual or computed fallback value")
    if pressure_target < 400:
        raise RecommendationAuditValidationError("P_blast_cold guidance cannot be below 400 kPa")
    pressure_max = _guidance_number(pressure_limits.get("normal_q3") or pressure_limits.get("hard_max"))
    if pressure_max is not None and pressure_target > pressure_max + 1e-6:
        raise RecommendationAuditValidationError("P_blast_cold guidance exceeds the current dynamic Q3 limit")
    if pci_target < 0 or pci_target > 45:
        raise RecommendationAuditValidationError("PCI_set guidance must be within 0-45 t/h")
    return {
        "furnace_id": str(body.get("furnace_id") or os.getenv("BF_FURNACE_ID", "GL02")).strip() or "GL02",
        "diagnosis_snapshot_id": body.get("diagnosis_snapshot_id"),
        "diagnosis_ts": diagnosis_ts,
        "diagnosis_main_label": str(body.get("diagnosis_main_label") or ""),
        "diagnosis_score": _guidance_number(body.get("diagnosis_score")),
        "cold_pressure_computed_target": computed_pressure,
        "cold_pressure_guidance_target": pressure_target,
        "cold_pressure_effective_at": body.get("cold_pressure_effective_at"),
        "pci_computed_target": computed_pci,
        "pci_guidance_target": pci_target,
        "pci_effective_at": body.get("pci_effective_at"),
        "pressure_limit_snapshot": pressure_limits,
        "pci_limit_snapshot": pci_limits,
        "pressure_source": pressure_source,
        "pci_source": pci_source,
        "approval_status": "confirmed",
        "entered_by": str(body.get("entered_by") or "值班工长"),
        "operator_note": str(body.get("operator_note") or ""),
        "request_payload": _json_safe(body),
    }


def persist_foreman_guidance(conn: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    record = normalize_foreman_guidance_request(request)
    row = conn.execute(
        f"""
        INSERT INTO {GUIDANCE_TABLE} (
            furnace_id, diagnosis_snapshot_id, diagnosis_ts, diagnosis_main_label,
            diagnosis_score, cold_pressure_computed_target, cold_pressure_guidance_target,
            cold_pressure_effective_at, pci_computed_target, pci_guidance_target,
            pci_effective_at, pressure_limit_snapshot, pci_limit_snapshot,
            pressure_source, pci_source, approval_status, entered_by, operator_note,
            request_payload
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb
        )
        RETURNING id, furnace_id, diagnosis_snapshot_id, diagnosis_ts,
                  cold_pressure_computed_target, cold_pressure_guidance_target,
                  cold_pressure_effective_at, pci_computed_target,
                  pci_guidance_target, pci_effective_at, pressure_source,
                  pci_source, approval_status, entered_by, operator_note, created_at
        """,
        (
            record["furnace_id"], record["diagnosis_snapshot_id"], record["diagnosis_ts"],
            record["diagnosis_main_label"], record["diagnosis_score"],
            record["cold_pressure_computed_target"], record["cold_pressure_guidance_target"],
            record["cold_pressure_effective_at"], record["pci_computed_target"],
            record["pci_guidance_target"], record["pci_effective_at"],
            _json_param(record["pressure_limit_snapshot"]), _json_param(record["pci_limit_snapshot"]),
            record["pressure_source"], record["pci_source"], record["approval_status"],
            record["entered_by"], record["operator_note"], _json_param(record["request_payload"]),
        ),
    ).fetchone()
    conn.commit()
    return {"state": "saved", "read_only": True, "guidance": dict(row) if row else record}


def latest_foreman_guidance(conn: Any, furnace_id: str | None = None) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT id, furnace_id, diagnosis_snapshot_id, diagnosis_ts,
               cold_pressure_computed_target, cold_pressure_guidance_target,
               cold_pressure_effective_at, pci_computed_target,
               pci_guidance_target, pci_effective_at, pressure_source,
               pci_source, approval_status, entered_by, operator_note, created_at
        FROM {GUIDANCE_TABLE}
        WHERE furnace_id = %s AND approval_status = 'confirmed'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(furnace_id or os.getenv("BF_FURNACE_ID", "GL02")).strip() or "GL02",),
    ).fetchone()
    if not row:
        return {"state": "none", "read_only": True, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
    item = dict(row)
    return {
        "state": "confirmed", "read_only": True,
        "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance",
        "id": item.get("id"), "diagnosis_ts": item.get("diagnosis_ts"),
        "entered_by": item.get("entered_by"), "operator_note": item.get("operator_note"),
        "targets": {"P_blast_cold": item.get("cold_pressure_guidance_target"), "PCI_set": item.get("pci_guidance_target")},
        "computed_targets": {"P_blast_cold": item.get("cold_pressure_computed_target"), "PCI_set": item.get("pci_computed_target")},
        "sources": {"P_blast_cold": item.get("pressure_source"), "PCI_set": item.get("pci_source")},
        "effective_at": {"P_blast_cold": item.get("cold_pressure_effective_at"), "PCI_set": item.get("pci_effective_at")},
        "created_at": item.get("created_at"),
    }


'@
if ($store.IndexOf("def normalize_foreman_guidance_request", [StringComparison]::Ordinal) -lt 0) { $store = $store.Replace($storeMarker, $storeInsert + $storeMarker) }
Save-Utf8 $storePath $store

$bridgePath = Join-Path $root "自动诊断服务\local_pg_ws_bridge.py"
$bridge = [System.IO.File]::ReadAllText($bridgePath, [Text.Encoding]::UTF8)
$bridge = $bridge.Replace(
    "from recommendation_audit_store import persist_recommendation_bundle  # noqa: E402",
    "from recommendation_audit_store import (" + [Environment]::NewLine + "    latest_foreman_guidance," + [Environment]::NewLine + "    persist_foreman_guidance," + [Environment]::NewLine + "    persist_recommendation_bundle," + [Environment]::NewLine + ")  # noqa: E402"
)
$payloadMarker = "    return payload" + [Environment]::NewLine + [Environment]::NewLine + "def fetch_diagnosis_history"
$payloadInsert = @'
    if audit_conn is not None:
        try:
            payload["foreman_guidance"] = latest_foreman_guidance(audit_conn)
        except Exception as exc:
            payload["foreman_guidance"] = {"state": "unavailable", "read_only": True, "reason": type(exc).__name__, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
    return payload


def save_foreman_guidance_request(request: dict[str, Any]) -> dict[str, Any]:
    with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
        return persist_foreman_guidance(conn, request)


def fetch_diagnosis_history
'@
if ($bridge.IndexOf("def save_foreman_guidance_request", [StringComparison]::Ordinal) -lt 0) { $bridge = $bridge.Replace($payloadMarker, $payloadInsert) }
$handlerMarker = "async def handle_chronos_request(websocket, request: dict[str, Any]) -> None:"
$handlerInsert = @'
async def handle_foreman_guidance_request(websocket, request: dict[str, Any]) -> bool:
    if request.get("type") != "foreman_guidance_save":
        return False
    request_id = request.get("request_id")
    try:
        result = await asyncio.to_thread(save_foreman_guidance_request, request)
        message = {"type": "foreman_guidance_saved", "request_id": request_id, **result}
    except Exception as exc:
        message = {"type": "foreman_guidance_error", "request_id": request_id, "state": "rejected", "read_only": True, "error_type": type(exc).__name__, "message": str(exc)}
    await websocket.send(json.dumps(message, ensure_ascii=False, default=json_default))
    return True


async def handle_chronos_request(websocket, request: dict[str, Any]) -> None:
'@
if ($bridge.IndexOf("async def handle_foreman_guidance_request", [StringComparison]::Ordinal) -lt 0) { $bridge = $bridge.Replace($handlerMarker, $handlerInsert) }
$bridge = $bridge.Replace("            await handle_chronos_request(websocket, request)", "            if await handle_foreman_guidance_request(websocket, request):" + [Environment]::NewLine + "                continue" + [Environment]::NewLine + "            await handle_chronos_request(websocket, request)")
Save-Utf8 $bridgePath $bridge

Write-Output "backend guidance patch applied"
