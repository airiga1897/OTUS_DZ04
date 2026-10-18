import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('run_logged', Path(__file__).resolve().parents[1] / 'scripts/run_logged.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LoggedProcessTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell integration')
    def test_windows_powershell_keeps_native_stderr_and_exit_code(self):
        engine = Path('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
        if not engine.exists():
            self.skipTest('Windows PowerShell unavailable')
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'probe.ps1'
            script.write_text("$ErrorActionPreference='Stop'\n& '" + sys.executable + "' -c \"import sys; print('stderr probe',file=sys.stderr); sys.exit(7)\"\n$taskCode=$LASTEXITCODE\nWrite-Output 'after native command'\nexit $taskCode\n", encoding='utf-8')
            log = Path(directory) / 'probe.log'
            code = module.run([str(engine), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)], log)
            self.assertEqual(code, 7)
            self.assertIn('stderr probe', log.read_text())
            self.assertIn('after native command', log.read_text())

    def test_stderr_is_preserved_and_failure_cannot_be_success(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'child.log'
            code = module.run([sys.executable, '-c', "import sys; print('output',flush=True); print('failure reason',file=sys.stderr); sys.exit(7)"], log)
            self.assertEqual(code, 7)
            self.assertIn('output', log.read_text())
            self.assertIn('failure reason', log.read_text())
