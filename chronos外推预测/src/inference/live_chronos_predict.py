import argparse
import json
import math
import os
from pathlib import Path
from statistics import median

import torch
from chronos import Chronos2Pipeline


def clean_values(values):
    cleaned = []
    last = None
    for value in values:
        try:
            number = float(value)
            if math.isnan(number) or math.isinf(number):
                number = last if last is not None else 0.0
        except (TypeError, ValueError):
            number = last if last is not None else 0.0
        cleaned.append(number)
        last = number
    return cleaned


def maybe_percent_series(target_id, context_values, forecast_values):
    """Keep GasUtil Chronos output in the same percent unit as the dashboard."""
    if target_id != "GasUtil":
        return [float(x) for x in forecast_values]
    context = [float(x) for x in context_values if math.isfinite(float(x))]
    forecast = [float(x) for x in forecast_values]
    finite_forecast = [x for x in forecast if math.isfinite(x)]
    if context and finite_forecast and max(abs(x) for x in context) > 1.5 and max(abs(x) for x in finite_forecast) <= 1.5:
        return [x * 100.0 if math.isfinite(x) else x for x in forecast]
    return forecast


def collapsed_zero_forecast(context_values, forecast_values):
    """Detect a model collapse without rejecting genuinely near-zero signals."""
    context = [abs(float(value)) for value in context_values if math.isfinite(float(value))]
    forecast = [abs(float(value)) for value in forecast_values if math.isfinite(float(value))]
    if not context or not forecast:
        return False
    level = median(context[-30:])
    if level <= 1e-6:
        return False
    tolerance = max(1e-9, level * 1e-8)
    return max(forecast) <= tolerance


def load_pipeline(model_path):
    dtype_name = os.getenv("BF_CHRONOS_DTYPE", "float32").strip().lower()
    device_name = os.getenv("BF_CHRONOS_DEVICE", "cpu").strip().lower()
    dtype_map = {
        "float32": torch.float32,
        "fp32": torch.float32,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float16": torch.float16,
        "fp16": torch.float16,
    }
    dtype = dtype_map.get(dtype_name, torch.float32)
    if device_name in {"cuda", "gpu"} and torch.cuda.is_available():
        device = "cuda"
    elif device_name == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = "cpu"
    return Chronos2Pipeline.from_pretrained(
        str(Path(model_path)),
        device_map=device,
        dtype=dtype,
    )


def run_prediction(pipeline, target_values, covariates, horizon):
    item = {"target": torch.tensor(target_values, dtype=torch.float32)}
    if covariates:
        item["past_covariates"] = covariates
    forecast = pipeline.predict([item], horizon)
    return forecast[0][0]


def quantile_series(target_id, target_values, target_quantiles):
    return {
        "p10": maybe_percent_series(target_id, target_values, target_quantiles[2].tolist()),
        "p50": maybe_percent_series(target_id, target_values, target_quantiles[10].tolist()),
        "p90": maybe_percent_series(target_id, target_values, target_quantiles[18].tolist()),
    }


def predict_one(pipeline, payload):
    horizon = int(payload.get("prediction_minutes", 30))
    target_id = payload["target"]["id"]
    target_values = clean_values(payload["target"]["values"])
    covariates = {}
    for item in payload.get("covariates", []):
        values = clean_values(item.get("values", []))
        if len(values) == len(target_values):
            covariates[item["id"]] = torch.tensor(values, dtype=torch.float32)

    initial_covariate_count = len(covariates)
    target_quantiles = run_prediction(pipeline, target_values, covariates, horizon)
    quantiles = quantile_series(target_id, target_values, target_quantiles)
    retry_reason = None
    if collapsed_zero_forecast(target_values, quantiles["p50"]) and covariates:
        retry_reason = "collapsed_zero_with_covariates"
        target_quantiles = run_prediction(pipeline, target_values, {}, horizon)
        quantiles = quantile_series(target_id, target_values, target_quantiles)
        covariates = {}

    common = {
        "target_id": target_id,
        "target_name": payload["target"].get("name", target_id),
        "priority": payload.get("priority"),
        "context_minutes": len(target_values),
        "prediction_minutes": horizon,
        "covariate_count": len(covariates),
        "initial_covariate_count": initial_covariate_count,
        "feature_type": payload.get("feature_type"),
        "feature_engine": payload.get("feature_engine"),
        "covariate_ids": list(covariates.keys()),
        "retry_reason": retry_reason,
    }
    if collapsed_zero_forecast(target_values, quantiles["p50"]):
        return {
            **common,
            "status": "error",
            "error": "collapsed_zero_forecast",
            "p10": [],
            "p50": [],
            "p90": [],
        }
    return {**common, "status": "success", **quantiles}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    pipeline = load_pipeline(args.model_path)
    if "jobs" in payload:
        predictions = []
        for job in payload["jobs"]:
            result = predict_one(pipeline, job)
            result["job_id"] = job.get("job_id")
            result["future_timestamps"] = job.get("future_timestamps", [])
            result["cutoff_time"] = job.get("cutoff_time")
            predictions.append(result)
        failed = [item["target_id"] for item in predictions if item.get("status") == "error"]
        result = {
            "status": "partial" if failed else "success",
            "prediction_count": len(predictions) - len(failed),
            "failed_prediction_count": len(failed),
            "failed_target_ids": failed,
            "predictions": predictions,
        }
    else:
        result = predict_one(pipeline, payload)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
