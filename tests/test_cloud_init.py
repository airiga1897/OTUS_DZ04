import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_cloud_init import completed


class CloudInitTests(unittest.TestCase):
    def test_recoverable_done_is_accepted(self):
        self.assertTrue(completed({'status': 'done', 'errors': [], 'recoverable_errors': {'WARNING': ['schema warning']}}, 2))

    def test_fatal_stage_or_incomplete_is_rejected(self):
        self.assertFalse(completed({'status': 'done', 'errors': [], 'modules-final': {'errors': ['failed']}}, 2))
        self.assertFalse(completed({'status': 'running', 'errors': []}, 0))
        self.assertFalse(completed({'status': 'done', 'errors': []}, 1))
