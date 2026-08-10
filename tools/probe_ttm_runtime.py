from __future__ import annotations

import argparse
import json

import torch
from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the locally installed IBM TTM runtime contract.")
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    model = TinyTimeMixerForPrediction.from_pretrained(args.model_path, local_files_only=True)
    model.eval()
    values = torch.linspace(0.0, 1.0, 512, dtype=torch.float32).reshape(1, 512, 1)
    with torch.no_grad():
        output = model(past_values=values, return_dict=True)
    shapes = {}
    for key, value in output.items():
        if hasattr(value, "shape"):
            shapes[key] = list(value.shape)
        else:
            shapes[key] = str(type(value).__name__)
    print(json.dumps({"config": model.config.to_dict(), "output_shapes": shapes}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
