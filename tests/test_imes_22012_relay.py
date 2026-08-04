from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "imes_22012_relay.py"
TOOLS_DIR = str(MODULE_PATH.parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
SPEC = importlib.util.spec_from_file_location("imes_22012_relay", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeChannel:
    def close(self):
        return None


class FakeTransport:
    def __init__(self, fail_port=None):
        self.fail_port = fail_port

    def open_channel(self, _kind, destination, _source, timeout=0):
        if destination[1] == self.fail_port:
            raise RuntimeError("blocked")
        return FakeChannel()


class RelayTests(unittest.TestCase):
    def test_default_profiles(self):
        self.assertEqual(len(MODULE.selected_relays("all", [])), 3)
        self.assertEqual(len(MODULE.selected_relays("imes", [])), 2)
        self.assertEqual([x.name for x in MODULE.selected_relays("pspace", [])], ["pspace"])

    def test_custom_forward_replaces_defaults(self):
        item = MODULE.parse_forward("demo:19000:10.0.0.2:9000")
        self.assertEqual(MODULE.selected_relays("all", [item]), [item])

    def test_invalid_forward_is_rejected(self):
        with self.assertRaises(Exception):
            MODULE.parse_forward("bad:port")

    def test_probe_relays_reports_each_target(self):
        results = MODULE.probe_relays(FakeTransport(fail_port=8889), MODULE.DEFAULT_RELAYS)
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[2]["ok"])
        self.assertNotIn("password", str(results).lower())


if __name__ == "__main__":
    unittest.main()
