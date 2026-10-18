import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from selectel_controller import select_disk

VOLUME = '12345678-1234-4234-8234-123456789012'
BY_ID = {'/dev/disk/by-id/volume-data': '/dev/sdb'}


class DiskIdentityTests(unittest.TestCase):
    def test_uuid_and_stable_path_required(self):
        disks = [{'name': '/dev/sdb', 'type': 'disk', 'serial': VOLUME, 'mountpoints': [None]}]
        self.assertEqual(select_disk(VOLUME, disks, BY_ID), '/dev/disk/by-id/volume-data')
        with self.assertRaises(ValueError):
            select_disk(VOLUME, disks, {})

    def test_boot_filesystem_rejected(self):
        disks = [{'name': '/dev/sdb', 'type': 'disk', 'serial': VOLUME,
                  'children': [{'mountpoints': ['/']}]}]
        with self.assertRaises(ValueError):
            select_disk(VOLUME, disks, BY_ID)

    def test_short_serial_and_ambiguous_disk_rejected(self):
        disk = {'name': '/dev/sdb', 'type': 'disk', 'serial': '12345678', 'mountpoints': []}
        with self.assertRaises(ValueError):
            select_disk(VOLUME, [disk], BY_ID)
        disk['serial'] = VOLUME
        with self.assertRaises(ValueError):
            select_disk(VOLUME, [disk, disk], BY_ID)

    def test_upload_can_identify_existing_gfs_mount(self):
        disks = [{'name': '/dev/sdb', 'type': 'disk', 'serial': VOLUME, 'mountpoints': ['/srv/otus']}]
        self.assertEqual(select_disk(VOLUME, disks, BY_ID), '/dev/disk/by-id/volume-data')
