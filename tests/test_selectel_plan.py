import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from selectel_plan import validate_creation


class CreationPlanTests(unittest.TestCase):
    def plan(self, actions):
        return {'resource_changes': [{'mode': 'managed', 'type': 'openstack_compute_instance_v2', 'change': {'actions': a}} for a in actions]}

    def test_resume_allows_existing_vms_without_replacement(self):
        self.assertEqual(len(validate_creation(self.plan([['create']] * 3 + [['no-op']] * 2))), 5)

    def test_update_delete_and_replacement_are_rejected(self):
        for action in (['update'], ['delete'], ['delete', 'create']):
            with self.assertRaises(ValueError):
                validate_creation(self.plan([['create']] * 4 + [action]))

    def test_wrong_vm_count_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_creation(self.plan([['create']] * 4))
