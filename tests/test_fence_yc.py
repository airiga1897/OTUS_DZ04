import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("fence_yc", Path(__file__).parents[1]/"scripts/fence_yc.py")
fence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fence)

class FenceTests(unittest.TestCase):
    def test_unknown_node_rejected_without_api(self):
        client = fence.FenceClient({"backend1": "id1"}, lambda *a: self.fail("API must not be called"), sleep=lambda n: None)
        with self.assertRaises(ValueError):
            client.off("db")

    def test_waits_for_stopped_and_checks_operation(self):
        calls = []
        states = iter(["RUNNING", "STOPPING", "STOPPED"])
        def api(method, path):
            calls.append((method, path))
            if method == "GET": return {"status": next(states)}
            return {"id": "op1"}
        client = fence.FenceClient({"backend1": "id1"}, api, sleep=lambda n: None)
        client.off("backend1")
        self.assertIn(("POST", "/instances/id1:stop"), calls)
        self.assertEqual(len(calls), 4)

    def test_failed_stop_cannot_be_success(self):
        def api(method, path):
            return {"status": "RUNNING"} if method == "GET" else {"error": {"code": 13}}
        client = fence.FenceClient({"backend1": "id1"}, api, sleep=lambda n: None)
        with self.assertRaises(RuntimeError): client.off("backend1")

    def test_running_forever_times_out(self):
        now = iter([0, 0, 200])
        client = fence.FenceClient({"backend1": "id1"}, lambda method, path: {"status": "RUNNING", "id": "op"},
                                  sleep=lambda n: None, clock=lambda: next(now), timeout=120)
        with self.assertRaises(TimeoutError): client.off("backend1")

if __name__ == "__main__": unittest.main()

