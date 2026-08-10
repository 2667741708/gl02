from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.patch_8093_core_metrics_pspace_live import (
    ASSET_NAME,
    MARKER,
    SCHEMA,
    SYSTEM_CLOCK_MARKER,
    patch_page,
)


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
ASSET = ROOT / "高炉前端数据" / "assets" / ASSET_NAME
DEPLOY = ROOT / "tools" / "remote_guarded_deploy_8093_core_metrics_pspace_live.ps1"
VERIFY_NODE = ROOT / "tools" / "verify_8093_core_metrics_pspace_live.cjs"


class CoreMetricPspaceLive8093Tests(unittest.TestCase):
    def test_realtime_asset_has_all_28_core_ids_and_server_bridge_contract(self) -> None:
        source = ASSET.read_text(encoding="utf-8")
        array_match = re.search(
            r"const CORE_IDS = Object\.freeze\(\[(.*?)\]\);",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(array_match)
        ids = re.findall(r'"([A-Za-z0-9_]+)"', array_match.group(1))
        self.assertEqual(28, len(ids))
        self.assertEqual(28, len(set(ids)))
        self.assertIn(f'const SCHEMA = "{SCHEMA}"', source)
        self.assertIn('"8770"', source)
        self.assertIn('new WebSocket(state.url)', source)
        self.assertIn('const pointMeta = payload.point_meta || {}', source)
        self.assertIn('source: "pspace_realtime_8770"', source)
        self.assertIn('const STALE_AFTER_MS = 12_000', source)
        self.assertIn('core_pspace_disabled', source)

    def test_page_uses_live_current_values_but_keeps_minute_history_for_sparks(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertEqual(2, page.count(MARKER))
        self.assertEqual(1, page.count(ASSET_NAME))
        self.assertIn("BFCoreMetricRowsPspaceLive8093", page)
        self.assertIn("BFCoreMetricRowPspaceLive8093", page)
        self.assertIn("coreMetricCurrent8093(buf, item, coreLive, coreNow)", page)
        self.assertIn("data-value-source={current.source}", page)
        self.assertIn("data-value-age-seconds={current.ageSeconds ?? ''}", page)
        self.assertIn("data-transport-age-seconds={transportAgeSeconds}", page)
        self.assertIn("data-value-quality={current.quality}", page)
        self.assertIn("已降级为分钟镜像", page)
        self.assertIn("<CoreMetricSparkButtonV1 buf={buf} item={item}", page)
        self.assertIn("coreDetailTrendOptionV1(buf, targetId, minutes)", page)

    def test_history_merge_is_timestamp_aligned_and_rejects_incomplete_series(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn("BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093", page)
        self.assertIn("values.length !== timestamps.length", page)
        self.assertIn("ignored_incomplete_trend_series", page)
        self.assertIn("strategy: 'timestamp_union_8768_primary_wins'", page)
        self.assertNotIn(
            "const history = Object.assign({}, msg.history || {}, trend.history || {});",
            page,
        )
        secondary_index = page.index("const merged = new Map(secondarySeries || []);")
        primary_index = page.index(
            "(primarySeries || []).forEach((value, timestamp) => merged.set(timestamp, value));"
        )
        self.assertLess(secondary_index, primary_index)

    def test_header_uses_wall_clock_and_labels_minute_data_separately(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertEqual(1, page.count(SYSTEM_CLOCK_MARKER))
        self.assertIn("const [systemTime, setSystemTime] = useState(() => new Date())", page)
        self.assertIn("const tick = () => setSystemTime(new Date())", page)
        self.assertIn("window.setInterval(tick, 1000)", page)
        self.assertIn("{fmtTime(systemTime)}", page)
        self.assertIn("分钟数据：", page)
        self.assertIn("{fmtTime(currentTime, 'hm')}", page)
        self.assertNotIn("const [displayTime, setDisplayTime] = useState(currentTime)", page)

    def test_patcher_is_idempotent(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertEqual(page, patch_page(page))

    def test_guarded_deployment_preserves_8768_8770_and_8094(self) -> None:
        script = DEPLOY.read_text(encoding="utf-8")
        self.assertTrue(script.isascii())
        self.assertIn('"BFV4PreviewProxy8093"', script)
        self.assertIn('"BFV4PreviewWs8768"', script)
        self.assertIn("Wait-PortState -Port 8093 -Listening $false", script)
        self.assertIn("pid_8768_unchanged", script)
        self.assertIn("pid_8770_unchanged", script)
        self.assertIn("html_8094_hash_unchanged", script)
        self.assertIn("shared_adapter_hash_unchanged", script)
        self.assertIn("camera_8094_hash_unchanged", script)
        self.assertIn("finally", script)
        self.assertIn("guard_restored", script)
        self.assertIn(SYSTEM_CLOCK_MARKER, script)

    def test_browser_verifier_checks_live_and_fallback_contracts(self) -> None:
        source = VERIFY_NODE.read_text(encoding="utf-8")
        self.assertIn("unique_core_ids", source)
        self.assertIn("dataset.valueSource", source)
        self.assertIn("dataset.valueAgeSeconds", source)
        self.assertIn("dataset.transportAgeSeconds", source)
        self.assertIn("dataset.valueQuality", source)
        self.assertIn("已降级为分钟镜像", source)
        self.assertIn("ALL_VIEWPORTS", source)
        self.assertIn("REPRESENTATIVE_VIEWPORTS", source)


if __name__ == "__main__":
    unittest.main()
