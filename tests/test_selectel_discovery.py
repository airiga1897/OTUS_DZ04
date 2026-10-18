import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("selectel_discovery", Path(__file__).resolve().parents[1] / "scripts/selectel-discover.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def service(kind, *urls):
    return {"type": kind, "endpoints": [{"interface": "public", "region": "ru-9", "url": url} for url in urls]}


class CatalogSelectionTests(unittest.TestCase):
    def test_unrelated_http_service_does_not_block_compute(self):
        endpoints, rejected = module.select_endpoints([
            service("unrelated", "http://unrelated.invalid"),
            service("compute", "https://compute.invalid/v2/project"),
        ], "ru-9", {"compute"})
        self.assertEqual(endpoints, {"compute": "https://compute.invalid/v2/project"})
        self.assertFalse(rejected)

    def test_http_never_replaces_https_and_http_only_is_rejected(self):
        endpoints, rejected = module.select_endpoints([
            service("compute", "https://compute.invalid/v2/project", "http://compute.invalid/v2/project"),
            service("network", "http://network.invalid"),
        ], "ru-9", {"compute", "network"})
        self.assertEqual(endpoints, {"compute": "https://compute.invalid/v2/project"})
        self.assertEqual(rejected, {"network"})


if __name__ == "__main__":
    unittest.main()
