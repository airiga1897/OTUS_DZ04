import ipaddress
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from selectel_admin_access import choose_cidrs, observed_ipv4


class AdminAccessTests(unittest.TestCase):
    def test_two_services_must_agree_on_global_ipv4(self):
        self.assertEqual(str(observed_ipv4(lambda _: '8.8.8.8')), '8.8.8.8')
        for values in [('8.8.8.8', '1.1.1.1'), ('127.0.0.1', '127.0.0.1')]:
            responses = iter(values)
            with self.assertRaises(ValueError):
                observed_ipv4(lambda _: next(responses))

    def test_stale_single_host_is_replaced_only_on_empty_state(self):
        address = ipaddress.IPv4Address('8.8.8.8')
        self.assertEqual(choose_cidrs(['1.1.1.1/32'], address), ['8.8.8.8/32'])
        with self.assertRaises(ValueError):
            choose_cidrs(['1.1.1.1/32'], address, existing=True)

    def test_existing_access_is_preserved_and_custom_lists_not_overwritten(self):
        address = ipaddress.IPv4Address('8.8.8.8')
        cidrs = ['8.8.8.0/24', '1.1.1.1/32']
        self.assertEqual(choose_cidrs(cidrs, address, existing=True), cidrs)
        for denied in [[], ['0.0.0.0/0'], ['1.1.1.0/24'], ['1.1.1.1/32', '9.9.9.9/32']]:
            with self.assertRaises(ValueError):
                choose_cidrs(denied, address)
