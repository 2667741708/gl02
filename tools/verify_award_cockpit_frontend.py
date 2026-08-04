"""调用 Node Playwright 验证 award-winning 风格高炉驾驶舱页面。

对应需求：
- REQ-20260527-AWARD-COCKPIT

本项目当前 `.venv` 不固定安装 Playwright Python 包；同机 Codex
runtime 自带 Node Playwright，因此该入口作为 Python 命令层包装器，
避免验证命令受 Python 虚拟环境影响。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_VERIFIER = ROOT / "tools" / "verify_award_cockpit_frontend_node.js"


def bundled_node() -> Path:
    """返回 Codex bundled Node；不存在时回退到 PATH 中的 node。"""

    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    candidate = home / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    return candidate if candidate.exists() else Path("node")


def main() -> int:
    cmd = [str(bundled_node()), str(NODE_VERIFIER), *sys.argv[1:]]
    completed = subprocess.run(cmd, cwd=ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
