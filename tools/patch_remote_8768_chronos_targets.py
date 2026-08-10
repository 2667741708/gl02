from __future__ import annotations

import argparse
import re
from pathlib import Path


TARGET_IDS = (
    "P_top",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "Q_blast",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "GasUtil",
    "DP_upper",
    "DP_lower",
    "DP_total",
    "PI",
)


def target_block() -> str:
    lines = ["CHRONOS_TARGET_IDS = ("]
    lines.extend(f'    "{target_id}",' for target_id in TARGET_IDS)
    lines.append(")")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch a downloaded production 8768 bridge to the 19-target contract.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_path = Path(args.input)
    output_path = Path(args.output)
    source = source_path.read_text(encoding="utf-8")
    pattern = re.compile(r"CHRONOS_TARGET_IDS\s*=\s*\(.*?\n\)", re.DOTALL)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise SystemExit(f"expected one CHRONOS_TARGET_IDS block, found {len(matches)}")

    patched = pattern.sub(target_block(), source, count=1)
    for target_id in TARGET_IDS:
        if f'"{target_id}"' not in patched:
            raise SystemExit(f"target was not written: {target_id}")
    if patched.count("CHRONOS_TARGET_IDS = (") != 1:
        raise SystemExit("target block is not unique after patch")
    compile(patched, str(output_path), "exec")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched, encoding="utf-8", newline="\n")
    print(
        {
            "input": str(source_path),
            "output": str(output_path),
            "changed": patched != source,
            "target_count": len(TARGET_IDS),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
