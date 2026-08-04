from __future__ import annotations

import json
import os

import psycopg


def main() -> int:
    result: dict[str, object] = {
        "env_present": {
            key: bool(os.getenv(key))
            for key in ("GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD")
        }
    }
    try:
        with psycopg.connect(
            host=os.getenv("GL02_PGHOST", "127.0.0.1"),
            port=int(os.getenv("GL02_PGPORT", "5432")),
            dbname=os.getenv("GL02_PGDATABASE", "bf_trend"),
            user=os.getenv("GL02_PGUSER", ""),
            password=os.getenv("GL02_PGPASSWORD", ""),
            connect_timeout=8,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user, version()")
                database, user, version = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT
                        to_regclass('bf_sensor.sensor_registry'),
                        to_regclass('bf_sensor.one_minute_values'),
                        to_regclass('bf_sensor.diagnosis_snapshots'),
                        to_regclass('public.t_ipes_cond'),
                        to_regclass('public.t_ipes_out_put')
                    """
                )
                registry, minute_values, diagnoses, heats, outputs = cursor.fetchone()
                result.update(
                    {
                        "connected": True,
                        "database": database,
                        "user": user,
                        "server_version_prefix": str(version).split(" on ")[0],
                        "relations": {
                            "bf_sensor.sensor_registry": bool(registry),
                            "bf_sensor.one_minute_values": bool(minute_values),
                            "bf_sensor.diagnosis_snapshots": bool(diagnoses),
                            "public.t_ipes_cond": bool(heats),
                            "public.t_ipes_out_put": bool(outputs),
                        },
                    }
                )
                for label, relation in (
                    ("sensor_registry_rows", "bf_sensor.sensor_registry"),
                    ("heat_rows_sample", "public.t_ipes_cond"),
                ):
                    cursor.execute(f"SELECT COUNT(*) FROM {relation}")
                    result[label] = int(cursor.fetchone()[0])
    except Exception as exc:  # noqa: BLE001
        result.update({"connected": False, "error_type": type(exc).__name__, "error": str(exc)})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("connected") else 1


if __name__ == "__main__":
    raise SystemExit(main())
