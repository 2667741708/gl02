from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from timeseries_model_contract import SCHEMA, extract_feature_vector, historical_fill, quantile


LOG = logging.getLogger("timeseries-sidecar")


class ModelStore:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

    def path(self, target_id: str, variant: str) -> Path:
        return self.model_dir / f"ridge_delta__{target_id}__{variant}.json"

    def load(self, target_id: str, variant: str) -> dict[str, Any]:
        path = self.path(target_id, variant)
        if not path.exists():
            raise FileNotFoundError(f"trained model not found: {path.name}")
        mtime = path.stat().st_mtime
        key = (target_id, variant)
        cached = self.cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        model = json.loads(path.read_text(encoding="utf-8"))
        if model.get("schema") != SCHEMA:
            raise ValueError(f"unsupported model schema: {model.get('schema')}")
        self.cache[key] = (mtime, model)
        return model

    def trained_models(self) -> list[dict[str, Any]]:
        output = []
        for path in sorted(self.model_dir.glob("ridge_delta__*.json")):
            try:
                model = json.loads(path.read_text(encoding="utf-8"))
                output.append({
                    "target_id": model.get("target_id"),
                    "variant": model.get("variant"),
                    "trained_at": model.get("trained_at"),
                    "path": path.name,
                })
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return output


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def upstream_status(base_url: str, timeout: float = 3.0) -> dict[str, Any]:
    try:
        with urlopen(Request(base_url.rstrip("/") + "/api/chronos/status"), timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        return {"reachable": True, "status": data}
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        return {"reachable": False, "error": str(exc)}


def job_parts(job: dict[str, Any]) -> tuple[str, str, list[Any], dict[str, list[Any]]]:
    target = job.get("target") or {}
    target_id = str(job.get("target_id") or job.get("job_id") or target.get("id") or "")
    if not target_id:
        raise ValueError("target_id is required")
    target_values = list(target.get("values") or job.get("values") or [])
    covariates = {
        str(item.get("id")): list(item.get("values") or [])
        for item in (job.get("covariates") or [])
        if item.get("id")
    }
    variant = str(job.get("variant") or ("expert_sparse" if covariates else "target_only"))
    return target_id, variant, target_values, covariates


def future_timestamps(job: dict[str, Any], horizon: int) -> list[str]:
    supplied = list(job.get("future_timestamps") or [])
    if len(supplied) >= horizon:
        return supplied[:horizon]
    cutoff = datetime.fromisoformat(str(job.get("cutoff_time") or datetime.now().isoformat()))
    return [(cutoff + timedelta(minutes=index)).isoformat(sep=" ") for index in range(1, horizon + 1)]


def local_interval(history: list[float], horizon: int) -> tuple[list[float], list[float]]:
    differences = [history[index] - history[index - 1] for index in range(1, len(history))]
    low_step = quantile(differences, 0.10)
    high_step = quantile(differences, 0.90)
    center_step = quantile(differences, 0.50)
    lows = []
    highs = []
    for index in range(1, horizon + 1):
        scale = math.sqrt(index)
        lows.append((low_step - center_step) * scale)
        highs.append((high_step - center_step) * scale)
    return lows, highs


def predict_baseline(job: dict[str, Any], model_name: str) -> dict[str, Any]:
    target_id, variant, values, covariates = job_parts(job)
    history = historical_fill(values)
    horizon = int(job.get("prediction_minutes") or 120)
    last = history[-1]
    if model_name == "linear_drift":
        recent = history[-30:]
        x_mean = (len(recent) - 1) / 2.0
        denominator = sum((index - x_mean) ** 2 for index in range(len(recent))) or 1.0
        slope = sum((index - x_mean) * (value - sum(recent) / len(recent)) for index, value in enumerate(recent)) / denominator
        p50 = [last + slope * index for index in range(1, horizon + 1)]
    else:
        p50 = [last] * horizon
    low_offsets, high_offsets = local_interval(history, horizon)
    return {
        "target_id": target_id,
        "target_name": (job.get("target") or {}).get("name") or target_id,
        "variant": variant,
        "model": model_name,
        "p10": [value + offset for value, offset in zip(p50, low_offsets)],
        "p50": p50,
        "p90": [value + offset for value, offset in zip(p50, high_offsets)],
        "future_timestamps": future_timestamps(job, horizon),
        "context_minutes": len(history),
        "prediction_minutes": horizon,
        "covariate_count": len(covariates),
        "feature_type": variant,
        "feature_engine": "TS-BENCHMARK-SIDECAR-20260808",
    }


def predict_ridge(job: dict[str, Any], store: ModelStore) -> dict[str, Any]:
    target_id, variant, target_values, covariates = job_parts(job)
    model = store.load(target_id, variant)
    covariate_ids = list(model.get("covariate_ids") or [])
    names, features = extract_feature_vector(target_values, covariates, covariate_ids)
    if names != model.get("feature_names"):
        raise ValueError("runtime features do not match trained model")
    center = model["x_center"]
    scale = model["x_scale"]
    standardized = [(value - center[index]) / scale[index] for index, value in enumerate(features)]
    coefficient = model["coefficient"]
    y_center = model["y_center"]
    horizon = len(y_center)
    delta = [
        y_center[step] + sum(standardized[index] * coefficient[index][step] for index in range(len(standardized)))
        for step in range(horizon)
    ]
    history = historical_fill(target_values)
    last = history[-1]
    p50 = [last + value for value in delta]
    p10 = [value + model["residual_q10"][index] for index, value in enumerate(p50)]
    p90 = [value + model["residual_q90"][index] for index, value in enumerate(p50)]
    return {
        "target_id": target_id,
        "target_name": (job.get("target") or {}).get("name") or target_id,
        "variant": variant,
        "model": "ridge_delta",
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "future_timestamps": future_timestamps(job, horizon),
        "context_minutes": len(history),
        "prediction_minutes": horizon,
        "covariate_count": len(covariate_ids),
        "feature_type": variant,
        "feature_engine": SCHEMA,
        "trained_at": model.get("trained_at"),
    }


class SidecarApplication:
    def __init__(self, model_dir: Path, chronos_url: str, default_model: str, timeout: float):
        self.store = ModelStore(model_dir)
        self.chronos_url = chronos_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.started = time.time()

    def model_catalog(self) -> list[dict[str, Any]]:
        trained = self.store.trained_models()
        return [
            {"id": "last_value", "status": "ready", "kind": "baseline"},
            {"id": "linear_drift", "status": "ready", "kind": "baseline"},
            {"id": "ridge_delta", "status": "ready" if trained else "awaiting_training", "kind": "local_supervised", "trained_models": len(trained)},
            {"id": "chronos2", "status": "ready" if upstream_status(self.chronos_url).get("reachable") else "unavailable", "kind": "foundation_proxy"},
            {"id": "tsmixerx", "status": "planned", "kind": "advanced_local"},
            {"id": "ibm_ttm", "status": "planned", "kind": "foundation_finetune"},
            {"id": "timesfm_2_5", "status": "planned", "kind": "foundation"},
            {"id": "patchtst", "status": "planned", "kind": "advanced_local"},
            {"id": "moirai_2", "status": "phase_3", "kind": "probabilistic_foundation"},
        ]

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "timeseries-model-benchmark-sidecar",
            "schema": "bf.timeseries.sidecar.8778.v1",
            "default_model": self.default_model,
            "model_dir": str(self.store.model_dir),
            "trained_model_count": len(self.store.trained_models()),
            "chronos_upstream": {"url": self.chronos_url, **upstream_status(self.chronos_url)},
            "uptime_seconds": round(time.time() - self.started, 1),
        }

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_name = str(payload.get("model") or self.default_model).lower()
        if model_name == "chronos2":
            result = post_json(self.chronos_url + "/api/chronos/predict", payload, self.timeout)
            result["sidecar_model"] = "chronos2"
            result["sidecar_port"] = 8778
            return result
        predictions = []
        errors = []
        started = time.perf_counter()
        for job in payload.get("jobs") or []:
            requested = str(job.get("model") or model_name).lower()
            try:
                if requested in ("last_value", "persistence"):
                    prediction = predict_baseline(job, "last_value")
                elif requested == "linear_drift":
                    prediction = predict_baseline(job, "linear_drift")
                elif requested == "ridge_delta":
                    prediction = predict_ridge(job, self.store)
                else:
                    raise ValueError(f"unsupported or not-yet-installed model: {requested}")
                predictions.append(prediction)
            except Exception as exc:  # noqa: BLE001
                errors.append({"target_id": job.get("target_id") or job.get("job_id"), "model": requested, "error": str(exc)})
        return {
            "status": "ok" if predictions else "failed",
            "type": "timeseries_prediction_batch",
            "engine": "benchmark-sidecar",
            "model": model_name,
            "prediction_count": len(predictions),
            "target_count": len(payload.get("jobs") or []),
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "predictions": predictions,
            "errors": errors,
        }


def handler_factory(application: SidecarApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BFTimeSeriesSidecar/1.0"

        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/api/timeseries/status", "/api/chronos/status"):
                self.send_json(200, application.status())
            elif self.path == "/api/timeseries/models":
                self.send_json(200, {"models": application.model_catalog()})
            else:
                self.send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/api/timeseries/predict", "/api/chronos/predict"):
                self.send_json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = application.predict(payload)
                self.send_json(200 if result.get("status") != "failed" else 422, result)
            except Exception as exc:  # noqa: BLE001
                LOG.exception("prediction request failed")
                self.send_json(500, {"status": "failed", "error": str(exc)})

        def log_message(self, message: str, *args: Any) -> None:
            LOG.info("%s %s", self.address_string(), message % args)

    return Handler


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the 8778 multi-model time-series benchmark sidecar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8778)
    parser.add_argument("--chronos-url", default="http://127.0.0.1:8777")
    parser.add_argument("--default-model", choices=["last_value", "linear_drift", "ridge_delta", "chronos2"], default="last_value")
    parser.add_argument("--model-dir", default=str(root / "PT" / "时间序列预测评测" / "models"))
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--log-file", default="")
    args = parser.parse_args()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    model_dir = Path(args.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    application = SidecarApplication(model_dir, args.chronos_url, args.default_model, args.timeout_seconds)
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(application))
    LOG.info("timeseries sidecar listening on http://%s:%s", args.host, args.port)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

