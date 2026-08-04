from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
BASE_DIR = BACKEND_DIR.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "proxy_8092.task.log"


def main() -> None:
    os.environ.setdefault("BF_PROXY_HOST", "0.0.0.0")
    os.environ.setdefault("BF_PROXY_PORT", "8092")
    os.environ.setdefault("BF_INDEX_FILE", "frontend_dashboard_v3.server.html")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://10.30.220.12:11434")
    os.environ.setdefault("BF_LLM_MODEL", "chiqiong-blast-furnace:latest")
    os.environ.setdefault("BF_FRONTEND_DIR", str(BASE_DIR))
    os.chdir(BASE_DIR)

    with LOG_PATH.open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = log
        sys.stderr = log
        try:
            import ollama_proxy_server

            ollama_proxy_server.main()
        except BaseException:  # noqa: BLE001
            traceback.print_exc()
            raise


if __name__ == "__main__":
    main()
