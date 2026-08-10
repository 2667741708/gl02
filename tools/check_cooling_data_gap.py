"""Check why cooling sensor data is sparse - compare with normal sensors."""
import psycopg, os
from psycopg.rows import dict_row
from pathlib import Path

# Resolve PG password — try env vars first, then env files
pw = os.environ.get("GL02_PGPASSWORD") or os.environ.get("PGPASSWORD")
if not pw:
    for env_file in [
        Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\PT\imes_vastbase.local.env"),
        Path(r"F:\高炉炼铁项目-real-sensor-v2_V3\PT\imes_vastbase.local.env"),
        Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\PT\external_sources.local.env"),
    ]:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "GL02_PGPASSWORD=" in line or "PGPASSWORD=" in line:
                    pw = line.split("=", 1)[1].strip()
                    break
        if pw: break
if not pw:
    # Last resort: try common Windows paths
    for p in [r"D:\文件\冀南钢铁运行中第二版本\PT\imes_vastbase.local.env"]:
        if Path(p).exists():
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                if "GL02_PGPASSWORD=" in line:
                    pw = line.split("=", 1)[1].strip()
                    break
        if pw: break
if not pw:
    print("ERROR: cannot resolve PG password from env or files")
    # Print what env files exist
    for d in [r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\PT", r"F:\高炉炼铁项目-real-sensor-v2_V3\PT"]:
        dp = Path(d)
        if dp.exists():
            print(f"  {d}: exists, files={list(dp.glob('*.env'))}")
        else:
            print(f"  {d}: NOT FOUND")
    exit(1)

c = psycopg.connect(host="127.0.0.1", port=5432, dbname="bf_trend", user="gl02_sync", password=pw, connect_timeout=10, row_factory=dict_row)

COOLING = ["Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel"]
NORMAL = ["P_blast", "Q_blast", "P_top", "DP_total", "T_blast", "GasUtil"]

print("=== Last 2 days: one_minute_values row counts ===")
for v in COOLING + NORMAL:
    r = c.execute(
        "SELECT count(*) n, min(ts) mn, max(ts) mx FROM bf_sensor.one_minute_values v2 "
        "JOIN bf_sensor.sensor_registry r2 ON r2.tag_long_name=v2.tag_long_name "
        "WHERE r2.variable_name=%s AND v2.ts >= now()-interval '2 days'", (v,)
    ).fetchone()
    expected = 2880  # 2 days * 1440 minutes
    pct = (r['n'] / expected * 100) if r and r['n'] else 0
    print(f"  {v:30s}: {r['n']:>6} rows / {expected} expected = {pct:.1f}%   [{str(r['mn'])[:19]} -> {str(r['mx'])[:19]}]" if r else f"  {v}: NO DATA")

print("\n=== raw_5s_values check (last 2 days) ===")
try:
    for v in COOLING[:3]:
        r = c.execute(
            "SELECT count(*) FROM bf_sensor.raw_5s_values WHERE "
            "tag_long_name=(SELECT tag_long_name FROM bf_sensor.sensor_registry WHERE variable_name=%s LIMIT 1) "
            "AND ts >= now()-interval '2 days'", (v,)
        ).fetchone()
        print(f"  {v}: {r['count']} raw 5s rows" if r else f"  {v}: NO RAW DATA")
except Exception as e:
    print(f"  raw_5s_values not accessible: {e}")

print("\n=== Yesterday (Aug 8): per-hour distribution ===")
for v in COOLING[:3] + NORMAL[:2]:
    rows = c.execute(
        "SELECT date_trunc('hour',v2.ts) AS h, count(*) n FROM bf_sensor.one_minute_values v2 "
        "JOIN bf_sensor.sensor_registry r2 ON r2.tag_long_name=v2.tag_long_name "
        "WHERE r2.variable_name=%s AND v2.ts >= '2026-08-08' AND v2.ts < '2026-08-09' "
        "GROUP BY h ORDER BY h", (v,)
    ).fetchall()
    hours_with_data = len(rows)
    max_per_hour = max(r['n'] for r in rows) if rows else 0
    print(f"  {v}: {hours_with_data}h with data, max {max_per_hour} rows/hour, total {sum(r['n'] for r in rows)} rows")

c.close()
