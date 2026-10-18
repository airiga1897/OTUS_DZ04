import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fence_selectel import FenceClient

NODES = {"backend1": "11111111-1111-4111-8111-111111111111", "backend2": "22222222-2222-4222-8222-222222222222"}


class SelectelFenceTests(unittest.TestCase):
    def test_unknown_node_never_calls_api(self):
        c = FenceClient(NODES, lambda *a: self.fail("Unexpected API call"))
        with self.assertRaises(ValueError):
            c.off("db")

    def test_stop_acceptance_is_not_confirmation(self):
        states = iter([("ACTIVE", 1), ("SHUTOFF", 1), ("SHUTOFF", 4)])
        calls = []
        def api(path, payload=None):
            calls.append((path, payload))
            if payload is not None:
                return {}
            status, power = next(states)
            return {"server": {"id": NODES["backend1"], "status": status, "OS-EXT-STS:power_state": power}}
        FenceClient(NODES, api, sleep=lambda n: None).off("backend1")
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[1][1], {"os-stop": None})

    def test_timeout_is_failure(self):
        clock = iter([0, 0, 200])
        def api(path, payload=None):
            return {} if payload is not None else {"server": {"id": NODES["backend1"], "status": "ACTIVE"}}
        with self.assertRaises(TimeoutError):
            FenceClient(NODES, api, clock=lambda: next(clock), sleep=lambda n: None).off("backend1")

    def test_wrong_uuid_is_failure(self):
        c = FenceClient(NODES, lambda *a: {"server": {"id": NODES["backend2"], "status": "SHUTOFF", "OS-EXT-STS:power_state": 4}})
        with self.assertRaises(ValueError):
            c.off("backend1")
