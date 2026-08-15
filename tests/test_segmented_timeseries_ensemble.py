import numpy as np

from tools.experiment_segmented_ensemble_19 import MODEL_NAMES, blend_forecasts, segmented_weights


def test_hard_segment_weights_use_expected_models():
    weights = segmented_weights(smooth=False)
    assert np.all(weights[:30, 0] == 1.0)
    assert np.all(weights[30:60, 1] == 1.0)
    assert np.all(weights[60:, 2] == 1.0)
    assert np.allclose(weights.sum(axis=1), 1.0)


def test_smooth_weights_are_convex_and_have_expected_anchors():
    weights = segmented_weights(smooth=True)
    assert np.all(weights >= 0.0)
    assert np.allclose(weights.sum(axis=1), 1.0)
    assert np.allclose(weights[29], [0.6, 0.4, 0.0])
    assert np.allclose(weights[30], [0.5, 0.5, 0.0])
    assert np.allclose(weights[59], [0.0, 0.6, 0.4])
    assert np.allclose(weights[60], [0.0, 0.5, 0.5])


def test_blend_uses_same_convex_weights_for_each_quantile():
    forecasts = {}
    for index, model in enumerate(MODEL_NAMES, 1):
        forecasts[model] = tuple(np.full(120, index * scale, dtype=float) for scale in (1, 2, 3))
    p10, p50, p90 = blend_forecasts(forecasts, smooth=True)
    assert p10[0] == 1.0
    assert p10[-1] == 3.0
    assert np.allclose(p50, p10 * 2.0)
    assert np.allclose(p90, p10 * 3.0)
