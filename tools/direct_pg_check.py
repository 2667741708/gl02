"""Direct PG check on 10.30.220.12:5432"""
import psycopg
from psycopg.rows import dict_row

# Password from AGENTS.md / ssh config
pw = "JNgt@2026"

conn = psycopg.connect(
    host="10.30.220.12", port=5432, dbname="bf_trend",
    user="postgres", password=pw, connect_timeout=10, row_factory=dict_row
)
print("Connected to PostgreSQL on 220.12\n")

# Check data volume for foreman vars
vars = ["Q_soft_water","P_soft_water","Q_high_pressure_water","P_high_pressure_water",
        "P_medium_pressure_water","ExpansionTankLevel","BlastEnergy","BlastSpeedStd",
        "BlastSpeedActual","Q_N2","P_N2","P_O2_valve_in","P_O2_valve_out",
        "Hopper_weight","CO_top","CO2_top","H2_top","PCI_previous_hour"]

print("=== one_minute_values data volume ===")
for v in vars:
    r = conn.execute("""
        SELECT count(*) n, min(ts) min_ts, max(ts) max_ts
        FROM bf_sensor.one_minute_values v2
        JOIN bf_sensor.sensor_registry r2 ON r2.tag_long_name = v2.tag_long_name
        WHERE r2.variable_name = %s
    """, (v,)).fetchone()
    if r and r['n']:
        days = (r['max_ts'] - r['min_ts']).days + 1
        print(f"  {v}: {r['n']:>6} rows, {days:>2}d ({str(r['min_ts'])[:10]} -> {str(r['max_ts'])[:10]})")
    else:
        print(f"  {v}: NO DATA")

print("\n=== daily_baselines for derived vars ===")
for v in ["T_taphole_mean","T_top"]:
    r = conn.execute("""
        SELECT count(*) n, max(baseline_day) latest
        FROM bf_sensor.daily_baselines
        WHERE baseline_days=30 AND variable_name=%s
    """, (v,)).fetchone()
    print(f"  {v}: {r['n']} days, latest={r['latest']}" if r else f"  {v}: NO BASELINE")

print("\n=== daily_baselines for cooling vars ===")
for v in ["Q_soft_water","P_soft_water","Q_high_pressure_water","P_high_pressure_water",
          "P_medium_pressure_water","ExpansionTankLevel"]:
    r = conn.execute("""
        SELECT count(*) n, max(baseline_day) latest
        FROM bf_sensor.daily_baselines
        WHERE baseline_days=30 AND variable_name=%s
    """, (v,)).fetchone()
    print(f"  {v}: {r['n']} days, latest={r['latest']}" if r else f"  {v}: NO BASELINE")

print("\n=== baseline count per day (last 5 days) ===")
rows = conn.execute("""
    SELECT baseline_day, count(*) n
    FROM bf_sensor.daily_baselines
    WHERE baseline_days=30 AND baseline_day >= current_date - 5
    GROUP BY baseline_day ORDER BY baseline_day DESC
""").fetchall()
for r in rows:
    print(f"  {r['baseline_day']}: {r['n']} variables")

conn.close()
