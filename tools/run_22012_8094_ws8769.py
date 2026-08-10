from __future__ import annotations

import os
import runpy
from pathlib import Path


ROOT = Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW")
PREVIEW_ROOT = ROOT / "preview_8094_ws8769"


def load_machine_database_environment() -> None:
    try:
        import winreg

        key_path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            for name in (
                "GL02_PGHOST",
                "GL02_PGPORT",
                "GL02_PGDATABASE",
                "GL02_PGUSER",
                "GL02_PGPASSWORD",
            ):
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                if value:
                    os.environ[name] = str(value)
    except OSError:
        pass


def main() -> None:
    load_machine_database_environment()
    os.environ.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "BF_WS_HOST": "0.0.0.0",
            "BF_WS_PORT": "8769",
            "BF_WS_HISTORY_HOURS": "8",
            "BF_WS_DIAGNOSIS_HISTORY_HOURS": "2",
            "BF_WS_TICK_SECONDS": "30",
            "BF_CHRONOS_BASE_URL": "http://127.0.0.1:8777",
            "BF_RECOMMENDATION_ENGINE_DIR": str(PREVIEW_ROOT / "recommendation_engine"),
        }
    )
    os.chdir(PREVIEW_ROOT)
    print("starting isolated 8094 preview WebSocket 8769 via direct Python task", flush=True)
    runpy.run_path(str(PREVIEW_ROOT / "local_pg_ws_bridge.py"), run_name="__main__")


if __name__ == "__main__":
    main()
