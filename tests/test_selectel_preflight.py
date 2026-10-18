import importlib.util
import io
import sys
import unittest
import urllib.error
import json
import tempfile
from unittest.mock import patch
from pathlib import Path

scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('preflight', scripts / 'selectel_preflight.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreflightTests(unittest.TestCase):
    def run_with_inactive_image(self, directory, existing=False):
        root = Path(directory)
        (root / '.local/selectel').mkdir(parents=True)
        (root / 'terraform-selectel').mkdir()
        (root / '.local/selectel/discovery.json').write_text(json.dumps({'project_id': 'project', 'region': 'ru-9'}))
        variables = root / 'terraform-selectel/terraform.tfvars.json'
        variables.write_text(json.dumps({'image_id': 'old', 'boot_disk_gb': 10}))
        if existing:
            (root / 'terraform-selectel/terraform.tfstate').write_text(json.dumps({'resources': [{'mode': 'managed', 'instances': [{}]}]}))
        catalog = [{'type': 'image', 'endpoints': [{'interface': 'public', 'region': 'ru-9', 'url': 'https://example.test/image'}]}]
        active = {'id': 'new', 'name': module.IMAGE_NAME, 'status': 'active', 'visibility': 'public', 'min_disk': 5}
        def response(url, **kwargs):
            return ({'id': 'old', 'status': 'deactivated', 'min_disk': 5} if '/images/old' in url else {'images': [active]}), {}
        with patch.object(module, 'ROOT', root), patch.object(module, 'config_from_env', return_value={'project_id': 'project', 'region': 'ru-9'}), patch.object(module, 'authenticate', return_value=('test-token', catalog)), patch.object(module.socket, 'getaddrinfo', return_value=[]), patch.object(module, 'request_json', side_effect=response):
            if existing:
                with self.assertRaises(ValueError):
                    module.main()
                self.assertEqual(json.loads(variables.read_text())['image_id'], 'old')
            else:
                module.main()
                self.assertEqual(json.loads(variables.read_text())['image_id'], 'new')

    def test_inactive_image_is_replaced_on_empty_state(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_with_inactive_image(directory)

    def test_inactive_image_never_replaces_existing_vms(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_with_inactive_image(directory, existing=True)

    def test_transient_timeout_is_retried_but_bounded(self):
        calls = []
        def unavailable():
            calls.append(True)
            raise TimeoutError()
        with self.assertRaises(RuntimeError):
            module.retry_read(unavailable, sleep=lambda _: None)
        self.assertEqual(len(calls), 3)

    def test_missing_image_is_not_hidden_by_network_retry(self):
        calls = []
        def missing():
            calls.append(True)
            raise urllib.error.HTTPError('https://example.test/image', 404, 'missing', {}, io.BytesIO())
        with self.assertRaises(urllib.error.HTTPError):
            module.retry_read(missing, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_replacement_must_be_unique_active_public_and_fit_disk(self):
        image = {'id': 'new', 'name': module.IMAGE_NAME, 'status': 'active', 'visibility': 'public', 'min_disk': 5}
        self.assertEqual(module.select_image([image], 10)['id'], 'new')
        for candidates in ([], [image, dict(image)], [dict(image, min_disk=20)], [dict(image, status='deleted')], [dict(image, visibility='private')]):
            with self.assertRaises(ValueError):
                module.select_image(candidates, 10)
