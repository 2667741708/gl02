"""Run pSpace backfill + baseline backfill on 220.12 in one shot."""
import psycopg, os, sys
from psycopg.rows import dict_row
from pathlib import Path

# Resolve PG credentials same way as store.py
def resolve_pg_password():
    for env_file in [
        Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\PT\imes_vastbase.local.env"),
        Path(r"F:\高炉炼铁项目-real-sensor-v2_V3\PT\imes_vastbase.local.env"),
    ]:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "GL02_PGPASSWORD=" in line:
                    return line.split("=", 1)[1].strip()
    return os.environ.get("GL02_PGPASSWORD", "")

PG_PASSWORD = resolve_pg_password()
PG = dict(
    host=os.environ.get("GL02_PGHOST", "127.0.0.1"),
    port=int(os.environ.get("GL02_PGPORT", "5432")),
    dbname=os.environ.get("GL02_PGDATABASE", "bf_trend"),
    user=os.environ.get("GL02_PGUSER", "gl02_sync"),
    password=PG_PASSWORD,
    connect_timeout=10,
    row_factory=dict_row,
)

VARS = ["Q_soft_water","P_soft_water","Q_high_pressure_water","P_high_pressure_water",
        "P_medium_pressure_water","ExpansionTankLevel","BlastEnergy","BlastSpeedStd",
        "BlastSpeedActual","Q_N2","P_N2","P_O2_valve_in","P_O2_valve_out",
        "Hopper_weight","CO_top","CO2_top","H2_top","PCI_previous_hour"]

def pg_check():
    print("=== BEFORE: one_minute_values data ===")
    conn = psycopg.connect(**PG)
    for v in VARS:
        r = conn.execute("SELECT count(*) n, min(ts) min_ts, max(ts) max_ts FROM bf_sensor.one_minute_values v2 JOIN bf_sensor.sensor_registry r2 ON r2.tag_long_name=v2.tag_long_name WHERE r2.variable_name=%s",(v,)).fetchone()
        if r and r['n']:
            days = (r['max_ts']-r['min_ts']).days+1
            print(f"  {v}: {r['n']:>6} rows, {days}d")
        else:
            print(f"  {v}: NO DATA")

    print("\n=== BEFORE: daily_baselines ===")
    for v in ["T_taphole_mean","T_top"] + VARS[:6]:
        r = conn.execute("SELECT count(*) n, max(baseline_day) latest FROM bf_sensor.daily_baselines WHERE baseline_days=30 AND variable_name=%s",(v,)).fetchone()
        print(f"  {v}: {r['n']}d baseline" if r and r['n'] else f"  {v}: NO BASELINE")
    conn.close()

def run_cmd(cmd):
    import subprocess
    print(f"\n=== Running: {cmd[:120]}... ===")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW", timeout=900)
    tail = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
    print(tail)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[-500:]}")
        print(f"WARNING: exit={result.returncode}")
    return result.returncode

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        pg_check()
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--baseline":
        pg_check()
        cmd2 = r'C:\Progra~1\Python311\python.exe 自动诊断服务\baseline_maintainer.py --backfill-days 30 --derived-only --write'
        rc2 = run_cmd(cmd2)
        print(f"\nStep 1 derived baseline: {'OK' if rc2==0 else 'FAILED (exit='+str(rc2)+')'}")
        cmd3 = r'C:\Progra~1\Python311\python.exe 自动诊断服务\baseline_maintainer.py --backfill-days 30 --cooling-only --write'
        rc3 = run_cmd(cmd3)
        print(f"\nStep 2 cooling baseline: {'OK' if rc3==0 else 'FAILED (exit='+str(rc3)+')'}")
        pg_check()
        print("\n=== BASELINE DONE ===")
        sys.exit(0)

    pg_check()

    # Step 1: pSpace 30-day backfill
    vars_str = ",".join(VARS)
    cmd1 = rf'C:\Progra~1\Python311\python.exe 数据库同步和存取\src\sync_from_243_pg.py --config 数据库同步和存取\config\sync_config.json --days 30 --chunk-hours 12 --batch-size 6 --max-workers 1 --source-mode processed --source-aggregate average --target-aggregate PS_HIS_AVERAGE --target-interval-seconds 60 --no-persist-raw-5s --variables {vars_str} --skip-retention'
    rc1 = run_cmd(cmd1)
    print(f"\nStep 1 pSpace backfill: {'OK' if rc1==0 else 'FAILED (exit='+str(rc1)+')'}")

    # Step 2: Derived baseline
    cmd2 = r'C:\Progra~1\Python311\python.exe 自动诊断服务\baseline_maintainer.py --backfill-days 30 --derived-only --write'
    rc2 = run_cmd(cmd2)
    print(f"\nStep 2 derived baseline: {'OK' if rc2==0 else 'FAILED (exit='+str(rc2)+')'}")

    # Step 3: Cooling baseline
    cmd3 = r'C:\Progra~1\Python311\python.exe 自动诊断服务\baseline_maintainer.py --backfill-days 30 --cooling-only --write'
    rc3 = run_cmd(cmd3)
    print(f"\nStep 3 cooling baseline: {'OK' if rc3==0 else 'FAILED (exit='+str(rc3)+')'}")

    pg_check()
    print("\n=== ALL DONE ===")
