# -*- coding: utf-8 -*-
"""Generate a PowerShell snippet that writes foreman trend assets from base64."""
from __future__ import annotations
import base64, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    ("foreman_trend_preview.html", ROOT / "高炉前端数据" / "foreman_trend_preview.html"),
    (r"assets\foreman-trend-preview.css", ROOT / "高炉前端数据" / "assets" / "foreman-trend-preview.css"),
    (r"assets\foreman-trend-preview.js", ROOT / "高炉前端数据" / "assets" / "foreman-trend-preview.js"),
]

lines = ['# Foreman trend asset writer - generated', '$dstRoot = $args[0]',
         'if (-not $dstRoot) { $dstRoot = "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\\高炉前端数据" }']

for rel, path in ASSETS:
    if not path.exists():
        print(f"MISSING: {path}", file=sys.stderr)
        sys.exit(1)
    b64 = base64.b64encode(path.read_bytes()).decode()
    dst = rel.replace('\\', '\\\\')
    lines.append(f'$b64 = "{b64}"')
    lines.append(f'$dst = Join-Path $dstRoot "{dst}"')
    lines.append(f'New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null')
    lines.append(f'[IO.File]::WriteAllBytes($dst, [Convert]::FromBase64String($b64))')
    lines.append(f'Write-Output "  wrote: {rel} ($([IO.FileInfo]::new($dst).Length) bytes)"')

print("\n".join(lines))
