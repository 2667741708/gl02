import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据/智能助手/backend"))
from mcp_host.cross_source_plan import CrossSourcePlan, CrossSourceStep

def step(name, deps=(), bindings=None):
    return CrossSourceStep(name, "read-source", "gl02", "query_gl02_sensors", {}, depends_on=deps, argument_bindings=bindings or {})

@pytest.mark.parametrize("path", ["steps.s1", "steps..value", "steps.s1.", "steps.s1..value", None])
def test_invalid_binding_is_rejected_before_execution(path):
    with pytest.raises(ValueError): step("s2", ("s1",), {"variable":path})

def test_binding_requires_declared_upstream_dependency():
    with pytest.raises(ValueError, match="declared dependency"):
        CrossSourcePlan(steps=(step("s1"),step("s2",bindings={"variable":"steps.s1.value"})))

def test_cycle_and_duplicate_dependencies_fail_at_plan_construction():
    with pytest.raises(ValueError, match="Cyclic"):
        CrossSourcePlan(steps=(step("s1",("s2",)),step("s2",("s1",))))
    with pytest.raises(ValueError, match="Duplicate dependency"):
        CrossSourcePlan(steps=(step("s1"),step("s2",("s1","s1"))))

def test_valid_graph_and_nested_binding_remain_supported():
    assert CrossSourcePlan(steps=(step("s1"),step("s2",("s1",),{"window":"steps.s1.time_window.start"}))).steps[1].depends_on == ("s1",)
