from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "chronos外推预测" / "src" / "inference" / "live_chronos_predict.py"


class FakeTensor(list):
    pass


def load_module():
    fake_torch = types.ModuleType("torch")
    fake_torch.float32 = "float32"
    fake_torch.bfloat16 = "bfloat16"
    fake_torch.float16 = "float16"
    fake_torch.tensor = lambda values, dtype=None: FakeTensor(values)
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    fake_chronos = types.ModuleType("chronos")
    fake_chronos.Chronos2Pipeline = object
    sys.modules["torch"] = fake_torch
    sys.modules["chronos"] = fake_chronos
    spec = importlib.util.spec_from_file_location("live_chronos_predict_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def quantiles(value: float, horizon: int):
    return [[[FakeTensor([value] * horizon) for _ in range(19)]]]


def payload():
    return {
        "target": {"id": "P_top", "name": "top pressure", "values": [250.0] * 60},
        "covariates": [{"id": "self", "values": [250.0] * 60}],
        "prediction_minutes": 5,
    }


def test_collapse_detection_distinguishes_real_zero_signal():
    module = load_module()
    assert module.collapsed_zero_forecast([250.0] * 30, [0.0] * 5)
    assert not module.collapsed_zero_forecast([0.0] * 30, [0.0] * 5)
    assert not module.collapsed_zero_forecast([250.0] * 30, [249.0] * 5)


def test_collapsed_covariate_forecast_retries_target_only():
    module = load_module()

    class Pipeline:
        def predict(self, model_input, horizon):
            return quantiles(0.0 if "past_covariates" in model_input[0] else 251.0, horizon)

    result = module.predict_one(Pipeline(), payload())
    assert result["status"] == "success"
    assert result["retry_reason"] == "collapsed_zero_with_covariates"
    assert result["initial_covariate_count"] == 1
    assert result["covariate_count"] == 0
    assert result["p50"] == [251.0] * 5


def test_persistent_collapse_returns_error_not_zero_curve():
    module = load_module()

    class Pipeline:
        def predict(self, model_input, horizon):
            return quantiles(0.0, horizon)

    result = module.predict_one(Pipeline(), payload())
    assert result["status"] == "error"
    assert result["error"] == "collapsed_zero_forecast"
    assert result["p50"] == []
