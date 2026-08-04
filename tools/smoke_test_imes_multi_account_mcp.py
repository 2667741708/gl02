"""Run live read-only smoke checks for the multi-account IMES MCP functions."""

from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_relay_mcp_server.py"
)


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "imes_relay_mcp_live_smoke", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load MCP module: {MODULE_PATH}")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    module.selectable_mes_objects.cache_clear()
    profiles = module.list_imes_database_profiles()
    operations_catalog = module.list_imes_business_objects("operations")
    laboratory_catalog = module.list_imes_business_objects("laboratory")
    operations_variables = module.query_imes_variables(
        object_name="public.t_ipes_out_put",
        variables=["workdate", "meltno", "ironquan", "workshift"],
        account_profile="operations",
        time_column="workdate",
        start_time="2026-07-25 00:00:00",
        end_time="2026-07-27 00:00:00",
        exact_filters={"prodcentercode": "2D012"},
        order_by="workdate",
        descending=True,
        row_limit=10,
    )
    laboratory_variables = module.query_imes_variables(
        object_name="public.v_qpes_sinter_machine_sample_insp_final",
        variables=[
            "试样单号",
            "业务日期",
            "加工中心编码",
            "tfevalue",
            "caovalue",
            "sio2value",
        ],
        account_profile="laboratory",
        time_column="业务日期",
        start_time="2025-04-21",
        end_time="2025-04-22",
        exact_filters={"加工中心编码": "JS2"},
        order_by="业务日期",
        descending=True,
        row_limit=10,
    )
    operations_sql = module.query_imes_readonly_sql(
        sql=(
            "SELECT workdate,meltno,ironquan "
            "FROM public.t_ipes_out_put "
            "WHERE workdate >= %s AND workdate < %s "
            "AND prodcentercode = %s "
            "ORDER BY workdate DESC"
        ),
        account_profile="operations",
        parameters=["2026-07-25", "2026-07-27", "2D012"],
        row_limit=5,
    )
    laboratory_sql = module.query_imes_readonly_sql(
        sql=(
            "SELECT sampleno,meltno,tfe,feo,cao,sio2 "
            "FROM public.v_qpes_slag_insoection_final "
            "WHERE meltno = %s"
        ),
        account_profile="laboratory",
        parameters=["2#20250126-328"],
        row_limit=5,
    )
    write_blocked = False
    try:
        module.query_imes_readonly_sql(
            "UPDATE public.t_ipes_cond SET meltno=meltno",
            account_profile="operations",
        )
    except ValueError:
        write_blocked = True
    report = {
        "requirement": "REQ-IMES-MULTI-ACCOUNT-ANY-READ-MCP-20260727",
        "checked_at": datetime.now().astimezone(),
        "profiles": profiles,
        "catalogs": {
            "operations": {
                "count": len(operations_catalog["objects"]),
                "objects": [
                    item["object"] for item in operations_catalog["objects"]
                ],
            },
            "laboratory": {
                "count": len(laboratory_catalog["objects"]),
                "objects": [
                    item["object"] for item in laboratory_catalog["objects"]
                ],
            },
        },
        "checks": {
            "operations_variable_rows": len(operations_variables["rows"]),
            "laboratory_variable_rows": len(laboratory_variables["rows"]),
            "operations_sql_rows": len(operations_sql["rows"]),
            "laboratory_sql_rows": len(laboratory_sql["rows"]),
            "write_sql_blocked": write_blocked,
            "all_results_readonly": all(
                item["read_policy"] == "readonly"
                for item in (
                    operations_variables,
                    laboratory_variables,
                    operations_sql,
                    laboratory_sql,
                )
            ),
        },
        "sample_results": {
            "operations_variables": operations_variables,
            "laboratory_variables": laboratory_variables,
            "operations_sql": operations_sql,
            "laboratory_sql": laboratory_sql,
        },
        "credentials_included": False,
    }
    output = ROOT / "logs" / "imes_multi_account_mcp_smoke_20260727.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    summary = {
        "output": str(output),
        "catalog_counts": {
            key: value["count"] for key, value in report["catalogs"].items()
        },
        **report["checks"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if all(
        (
            report["checks"]["operations_variable_rows"] > 0,
            report["checks"]["laboratory_variable_rows"] > 0,
            report["checks"]["operations_sql_rows"] > 0,
            report["checks"]["laboratory_sql_rows"] > 0,
            report["checks"]["write_sql_blocked"],
            report["checks"]["all_results_readonly"],
        )
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
