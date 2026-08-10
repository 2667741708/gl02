"""Probe baseline coverage for ABC33 critical variables on 220.12."""
from __future__ import annotations

import json
import os
import psycopg
from psycopg.rows import dict_row

VARS = [
    "T_taphole_mean", "T_top", "TFT", "BlastEnergy", "BlastSpeedStd", "BlastSpeedActual",
    "Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water",
    "P_medium_pressure_water", "ExpansionTankLevel",
    "Q_N2", "P_N2", "P_O2_valve_in", "P_O2_valve_out",
    "Hopper_weight", "Hopper_weight_set",
    "T_taphole_1", "T_taphole_2",
    "PCI_rate", "PCI_set", "O2_rate", "Q_O2", "T_blast", "P_blast_cold",
    "CO_top", "CO2_top", "H2_top", "PCI_previous_hour", "PCI_current_hour",
]

pg_host = os.environ.get("GL02_PGHOST", "127.0.0.1")
pg_port = int(os.environ.get("GL02_PGPORT", "5432"))
pg_user = os.environ.get("GL02_PGUSER", "")
pg_password = os.environ.get("GL02_PGPASSWORD", "")
if not pg_password:
    # Try reading from project env file
    env_path = r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\PT\imes_vastbase.local.env"
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("GL02_PGPASSWORD="):
                pg_password = line.split("=", 1)[1].strip()
                break

conn = psycopg.connect(
    host=pg_host, port=pg_port, dbname="bf_trend",
    user=pg_user, password=pg_password,
    connect_timeout=5, row_factory=dict_row,
)

rows = conn.execute(
    """SELECT variable_name, count(*) AS days, max(baseline_day) AS latest_day
       FROM bf_sensor.daily_baselines
       WHERE baseline_days = 30 AND variable_name = ANY(%s)
       GROUP BY variable_name ORDER BY days DESC""",
    (VARS,),
).fetchall()

found = {r["variable_name"] for r in rows}
missing = [v for v in VARS if v not in found]

print(json.dumps({
    "found": {r["variable_name"]: {"days": r["days"], "latest": str(r["latest_day"])} for r in rows},
    "missing": missing,
    "total_checked": len(VARS),
    "found_count": len(rows),
    "missing_count": len(missing),
}, ensure_ascii=False, indent=2))
