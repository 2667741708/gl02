from si_semantic_engine.train_v18 import _specs


def test_v18_specs_are_bounded_plain_residual_models() -> None:
    specs = _specs()
    assert {spec.loss_function for spec in specs} == {"MAE", "RMSE"}
    assert all(spec.boosting_type == "Plain" for spec in specs)
    assert all(spec.target_mode == "residual" for spec in specs)
    assert all(spec.iterations <= 200 for spec in specs)
