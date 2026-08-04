#!/usr/bin/env python3
"""Fallback deployment of the 8093 dual camera runtime over Windows SMB.

Use only when the mandated SSH helper cannot finish within the user's short
command timeout. Credentials are read from the existing authorized AGENTS.md
entry or environment and are never written to the deployment payload/log.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
sys.path.insert(0, str(ROOT))

from tools.remote_deploy_8093_dual_camera_modes import deploy


class NETRESOURCEW(ctypes.Structure):
    _fields_ = (
        ("dwScope", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("dwDisplayType", wintypes.DWORD),
        ("dwUsage", wintypes.DWORD),
        ("lpLocalName", wintypes.LPWSTR),
        ("lpRemoteName", wintypes.LPWSTR),
        ("lpComment", wintypes.LPWSTR),
        ("lpProvider", wintypes.LPWSTR),
    )


def resolve_password(allow_agents_password: bool) -> str:
    value = os.getenv("BF_22012_SSH_PASSWORD")
    if value:
        return value
    if allow_agents_password and AGENTS.is_file():
        text = AGENTS.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"SSH 密码：([^\r\n]+)", text)
        if match:
            return match.group(1).strip()
    raise RuntimeError(
        "missing authorized 220.12 credential; set BF_22012_SSH_PASSWORD "
        "or pass --allow-agents-password"
    )


def connect_share(share: str, username: str, password: str) -> None:
    resource = NETRESOURCEW()
    resource.dwType = 1  # RESOURCETYPE_DISK
    resource.lpRemoteName = share
    result = ctypes.windll.mpr.WNetAddConnection2W(
        ctypes.byref(resource), password, username, 0
    )
    if result != 0:
        raise OSError(result, f"WNetAddConnection2W failed for {share}")


def disconnect_share(share: str) -> None:
    result = ctypes.windll.mpr.WNetCancelConnection2W(share, 0, True)
    if result not in (0, 2250):  # success or ERROR_NOT_CONNECTED
        raise OSError(result, f"WNetCancelConnection2W failed for {share}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="10.30.220.12")
    parser.add_argument("--user", default="administrator")
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument(
        "--payload",
        type=Path,
        default=ROOT / "高炉前端数据" / "assets" / "bf3d-surface-camera-guard-8093.js",
    )
    args = parser.parse_args()
    share = rf"\\{args.host}\F$"
    remote_root = Path(share) / "高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
    password = resolve_password(args.allow_agents_password)
    connected = False
    try:
        connect_share(share, args.user, password)
        connected = True
        result = deploy(remote_root, args.payload.resolve())
        print(
            "deployed={deployed} schema={schema} marker={marker} "
            "8094_unchanged={unchanged} backup={backup}".format(
                deployed=result["deployed"],
                schema=result["schema"],
                marker=result["marker"],
                unchanged=result["8094_unchanged"],
                backup=result["backup"],
            )
        )
    finally:
        if connected:
            disconnect_share(share)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
