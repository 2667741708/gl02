from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import imes_web_launcher as launcher  # noqa: E402


def test_relay_command_covers_web_and_vastbase_and_stays_loopback() -> None:
    command = launcher.build_relay_command("python-test")
    assert command[:2] == ["python-test", str(launcher.RELAY_SCRIPT)]
    assert "--profile" in command
    assert command[command.index("--profile") + 1] == "imes"
    assert "--forward" not in command
    assert "127.0.0.1" not in command


def test_python_environment_does_not_add_credentials() -> None:
    env = launcher.python_environment()
    assert env.get("PYTHONUTF8") == "1"
    assert "BF_22012_SSH_PASSWORD" not in env or env["BF_22012_SSH_PASSWORD"] == os.environ.get(
        "BF_22012_SSH_PASSWORD"
    )
