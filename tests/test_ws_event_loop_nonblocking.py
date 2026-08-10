from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_8768_database_reads_do_not_block_websocket_event_loop():
    source = (ROOT / "自动诊断服务" / "local_pg_ws_bridge.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(build_init_payload)" in source
    assert "await asyncio.to_thread(build_tick_payload)" in source


def test_8770_pspace_reads_do_not_block_websocket_event_loop():
    source = (ROOT / "tools" / "pspace_8092_realtime_bridge.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(self.build_init_payload)" in source
    assert "await asyncio.to_thread(self.read_frame)" in source
