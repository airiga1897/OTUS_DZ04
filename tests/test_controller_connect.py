import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import controller


class ControllerConnectTests(unittest.TestCase):
    def test_temporary_tcp_failure_is_retried_with_trusted_keys(self):
        first, second = MagicMock(), MagicMock()
        first.connect.side_effect = TimeoutError()
        with patch.object(controller.paramiko, 'SSHClient', side_effect=[first, second]), patch.object(controller.time, 'sleep'):
            result = controller.connect({'lb_public_ip': '192.0.2.1', 'ssh_user': 'otus', 'admin_ssh_port': 443})
        self.assertIs(result, second)
        self.assertEqual(second.connect.call_args.kwargs['port'], 443)
        first.close.assert_called_once()
        self.assertIsInstance(second.set_missing_host_key_policy.call_args.args[0], controller.paramiko.RejectPolicy)

    def test_authentication_failure_is_not_retried(self):
        client = MagicMock()
        client.connect.side_effect = controller.paramiko.AuthenticationException('test')
        with patch.object(controller.paramiko, 'SSHClient', return_value=client) as factory:
            with self.assertRaises(controller.paramiko.AuthenticationException):
                controller.connect({'lb_public_ip': '192.0.2.1', 'ssh_user': 'otus'})
        self.assertEqual(factory.call_count, 1)
        client.close.assert_called_once()

    def test_tcp_retries_are_bounded(self):
        client = MagicMock()
        client.connect.side_effect = TimeoutError()
        with patch.object(controller.paramiko, 'SSHClient', return_value=client), patch.object(controller.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, '6 попыток'):
                controller.connect({'lb_public_ip': '192.0.2.1', 'ssh_user': 'otus'})
        self.assertEqual(client.connect.call_count, 6)
