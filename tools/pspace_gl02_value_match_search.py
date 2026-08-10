"""One-shot GL02 pSpace search by observed HMI values, then fetch candidate descriptions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tools"))
from pspace_8092_realtime_bridge import (
    find_sdk_root,
    get_tag_props,
    load_sdk,
    query_all_tag_names,
    read_realtime,
)
from pspace_8092_realtime_bridge import connect_pspace
from run_billboard_pspace_8770 import load_credentials


ROOT = "\\冀南钢铁\\SIO\\GL02\\"
TARGETS = {
    "Q_soft_water": (4431.0, 180.0),
    "P_soft_water": (0.80, 0.035),
    "Q_high_pressure_water": (882.0, 45.0),
    "P_high_pressure_water": (1.58, 0.055),
    "P_medium_pressure_water": (0.87, 0.045),
    "ExpansionTankLevel": (3.7, 0.22),
    "Hopper_weight": (28.5, 12.0),
    "Q_N2": (1312.0, 90.0),
    "P_N2": (614.6, 35.0),
    "P_O2_valve_in": (0.67, 0.035),
    "P_O2_valve_out": (0.49, 0.035),
    "Q_O2": (20103.0, 900.0),
    "O2_rate": (6.705, 0.45),
    "TFT": (2152.0, 90.0),
}


class Args:
    pspace_server = os.getenv("PSPACE_SERVER", "10.22.181.244")
    pspace_port = os.getenv("PSPACE_PORT", "8889")
    pspace_user: str | None = None
    pspace_password: str | None = None


def main() -> None:
    args = Args()
    args.pspace_user, args.pspace_password = load_credentials()
    sdk_root = find_sdk_root(os.getenv("PSPACE_SDK_ROOT"))
    PsObject, T = load_sdk(sdk_root)
    pspace = connect_pspace(PsObject, T, args)
    tags = [tag for tag in query_all_tag_names(pspace, T) if tag.startswith(ROOT)]
    values: dict[str, float | None] = {}
    timestamps: dict[str, str] = {}
    qualities: dict[str, str] = {}
    skipped: list[str] = []

    def read_batch(batch: list[str]) -> None:
        if not batch:
            return
        try:
            batch_values, batch_meta = read_realtime(pspace, T, {tag: tag for tag in batch})
        except RuntimeError:
            if len(batch) == 1:
                skipped.append(batch[0])
                return
            middle = len(batch) // 2
            read_batch(batch[:middle])
            read_batch(batch[middle:])
            return
        values.update(batch_values)
        timestamps.update(batch_meta.get("timestamps") or {})
        qualities.update(batch_meta.get("qualities") or {})

    for start in range(0, len(tags), 20):
        read_batch(tags[start : start + 20])
    rows = []
    for tag in tags:
        value = values.get(tag)
        if not isinstance(value, (int, float)):
            continue
        matched = []
        for sensor_id, (target, tolerance) in TARGETS.items():
            difference = abs(float(value) - target)
            if difference <= tolerance:
                matched.append({"sensor_id": sensor_id, "target": target, "difference": difference})
        if not matched:
            continue
        props = get_tag_props(pspace, T, tag)
        rows.append({
            "tag": tag,
            "name": props.get("name", ""),
            "description": props.get("description", ""),
            "unit": props.get("unit", ""),
            "value": value,
            "timestamp": timestamps.get(tag, ""),
            "quality": qualities.get(tag, ""),
            "matched": sorted(matched, key=lambda item: item["difference"]),
        })
    rows.sort(key=lambda row: (row["matched"][0]["sensor_id"], row["matched"][0]["difference"]))
    output = Path(r"C:\Users\Administrator\AppData\Local\Temp\foreman_gl02_value_match_20260806.json")
    output.write_text(json.dumps({"tag_count": len(tags), "skipped": skipped, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tag_count": len(tags), "skipped": len(skipped), "matches": len(rows), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
