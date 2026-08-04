"""Pure-Python inference kernel for the semantic-neuron Si model.

The module intentionally contains no training or production database access.
It evaluates an already calibrated, versioned configuration and returns an
auditable probability distribution.

Requirement:
    REQ-SI-SEMANTIC-NEURON-ENGINE-20260726
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, isfinite, sqrt
from typing import Any, Mapping


class ModelConfigError(ValueError):
    """Raised when a semantic-neuron configuration is invalid."""


class ModelNotCalibratedError(RuntimeError):
    """Raised when an unfitted or retired model is asked to predict."""


class FeatureValidationError(ValueError):
    """Raised when required numeric input features are absent or invalid."""


INFERENCE_ALLOWED_STATUSES = frozenset(
    {"calibrated_experimental", "shadow_validated", "approved_readonly"}
)


def _normal_cdf(value: float, mean: float, std: float) -> float:
    return 0.5 * (1.0 + erf((value - mean) / (std * sqrt(2.0))))


def _sigmoid(value: float) -> float:
    if value >= 0:
        tail = exp(-value)
        return 1.0 / (1.0 + tail)
    head = exp(value)
    return head / (1.0 + head)


def _finite_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FeatureValidationError(f"特征 {name!r} 不是有效数值") from exc
    if not isfinite(number):
        raise FeatureValidationError(f"特征 {name!r} 不是有限数值")
    return number


@dataclass(frozen=True)
class SemanticNeuron:
    """One process-meaningful, inspectable nonlinear unit."""

    neuron_id: str
    display_name: str
    feature_weights: Mapping[str, float]
    threshold: float
    scale: float
    output_weight: float
    neutral_activation: float = 0.5
    expected_direction: str = "unconstrained"

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "SemanticNeuron":
        neuron_id = str(item.get("id") or "").strip()
        if not neuron_id:
            raise ModelConfigError("神经元缺少 id")
        raw_weights = item.get("feature_weights")
        if not isinstance(raw_weights, Mapping) or not raw_weights:
            raise ModelConfigError(f"神经元 {neuron_id!r} 缺少 feature_weights")
        weights = {str(key): float(value) for key, value in raw_weights.items()}
        scale = float(item.get("scale", 1.0))
        if not isfinite(scale) or scale <= 0:
            raise ModelConfigError(f"神经元 {neuron_id!r} 的 scale 必须大于0")
        neutral = float(item.get("neutral_activation", 0.5))
        if not 0.0 <= neutral <= 1.0:
            raise ModelConfigError(
                f"神经元 {neuron_id!r} 的 neutral_activation 必须在0到1之间"
            )
        return cls(
            neuron_id=neuron_id,
            display_name=str(item.get("display_name") or neuron_id),
            feature_weights=weights,
            threshold=float(item.get("threshold", 0.0)),
            scale=scale,
            output_weight=float(item.get("output_weight", 0.0)),
            neutral_activation=neutral,
            expected_direction=str(
                item.get("expected_direction") or "unconstrained"
            ),
        )

    def evaluate(self, features: Mapping[str, Any]) -> dict[str, Any]:
        missing = [name for name in self.feature_weights if name not in features]
        if missing:
            raise FeatureValidationError(
                f"神经元 {self.neuron_id!r} 缺少特征：{', '.join(missing)}"
            )
        weighted_inputs: dict[str, float] = {}
        raw_response = 0.0
        for name, weight in self.feature_weights.items():
            value = _finite_number(features[name], name)
            weighted = float(weight) * value
            weighted_inputs[name] = weighted
            raw_response += weighted
        activation = _sigmoid((raw_response - self.threshold) / self.scale)
        contribution = self.output_weight * (
            activation - self.neutral_activation
        )
        return {
            "id": self.neuron_id,
            "display_name": self.display_name,
            "expected_direction": self.expected_direction,
            "raw_response": raw_response,
            "threshold": self.threshold,
            "scale": self.scale,
            "activation": activation,
            "neutral_activation": self.neutral_activation,
            "output_weight": self.output_weight,
            "contribution_to_si_pct": contribution,
            "weighted_inputs": weighted_inputs,
        }


@dataclass(frozen=True)
class SemanticSiEngine:
    """Versioned semantic-neuron ensemble with calibrated residual uncertainty."""

    model_id: str
    model_version: str
    model_status: str
    intercept: float
    residual_std: float
    target_low: float
    target_high: float
    neurons: tuple[SemanticNeuron, ...]
    unit: str = "%"
    distribution_family: str = "normal"

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "SemanticSiEngine":
        raw_neurons = config.get("neurons")
        if not isinstance(raw_neurons, list) or not raw_neurons:
            raise ModelConfigError("配置必须包含非空 neurons 数组")
        neurons = tuple(SemanticNeuron.from_mapping(item) for item in raw_neurons)
        neuron_ids = [item.neuron_id for item in neurons]
        if len(neuron_ids) != len(set(neuron_ids)):
            raise ModelConfigError("神经元 id 必须唯一")
        residual_std = float(config.get("residual_std", 0.0))
        if not isfinite(residual_std) or residual_std <= 0:
            raise ModelConfigError("residual_std 必须是大于0的标定值")
        band = config.get("target_band") or {}
        low = float(band.get("low", 0.20))
        high = float(band.get("high", 0.40))
        if not low < high:
            raise ModelConfigError("target_band.low 必须小于 target_band.high")
        family = str(config.get("distribution_family") or "normal")
        if family != "normal":
            raise ModelConfigError("当前内核只支持 normal 分布")
        return cls(
            model_id=str(config.get("model_id") or "semantic_si_engine"),
            model_version=str(config.get("model_version") or "unversioned"),
            model_status=str(config.get("model_status") or "design_only_unfitted"),
            intercept=float(config.get("intercept", 0.0)),
            residual_std=residual_std,
            target_low=low,
            target_high=high,
            neurons=neurons,
            unit=str(config.get("unit") or "%"),
            distribution_family=family,
        )

    def predict(self, features: Mapping[str, Any]) -> dict[str, Any]:
        """Return Si distribution and traceable neuron contributions.

        Raises:
            ModelNotCalibratedError: configuration is not permitted to infer.
            FeatureValidationError: a required feature is missing or invalid.
        """

        if self.model_status not in INFERENCE_ALLOWED_STATUSES:
            raise ModelNotCalibratedError(
                f"模型状态 {self.model_status!r} 不允许输出预测；"
                "请先完成训练、时间回测和残差分布标定"
            )
        neuron_results = [neuron.evaluate(features) for neuron in self.neurons]
        mean = self.intercept + sum(
            item["contribution_to_si_pct"] for item in neuron_results
        )
        std = self.residual_std
        probability_below = _normal_cdf(self.target_low, mean, std)
        probability_at_or_below_high = _normal_cdf(
            self.target_high, mean, std
        )
        probability_target = max(
            0.0, probability_at_or_below_high - probability_below
        )
        probability_above = max(0.0, 1.0 - probability_at_or_below_high)
        probability_total = (
            probability_below + probability_target + probability_above
        )
        if probability_total <= 0:
            raise ModelConfigError("预测概率总和异常")
        probabilities = {
            "below_target": probability_below / probability_total,
            "within_target": probability_target / probability_total,
            "above_target": probability_above / probability_total,
        }
        z90 = 1.2815515655446004
        ranked = sorted(
            neuron_results,
            key=lambda item: abs(item["contribution_to_si_pct"]),
            reverse=True,
        )
        return {
            "model": {
                "id": self.model_id,
                "version": self.model_version,
                "status": self.model_status,
            },
            "target": {
                "name": "hot_metal_Si",
                "unit": self.unit,
                "target_band": {
                    "low": self.target_low,
                    "high": self.target_high,
                },
            },
            "distribution": {
                "family": self.distribution_family,
                "mean": mean,
                "std": std,
                "p10": mean - z90 * std,
                "p50": mean,
                "p90": mean + z90 * std,
                "probabilities": probabilities,
            },
            "neurons": ranked,
        }

