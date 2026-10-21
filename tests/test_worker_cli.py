"""Offline CLI diagnostics: mocks plus harmless bounded Python subprocesses."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.ci import check_worker_cli as worker


def fake_capture(argv, cwd, env, seconds):
    raw = b'2.1.280' if argv[-1] == '--version' else b'--help --print --sandbox --mode plan accept-edits --trust'
    return {'status': 'PASS', 'exit_code': 0}, raw


class WorkerCliTests(unittest.TestCase):
    def test_default_does_not_launch_any_cli(self):
        with patch.object(worker.shutil, 'which', return_value='/installed/cli'), \
             patch.object(worker, 'capture') as capture:
            report = worker.diagnose()
        capture.assert_not_called()
        self.assertEqual(report['subprocess_count'], 0)
        self.assertEqual(report['status'], 'PASS')
        self.assertTrue(all(x['status'] == 'DISCOVERED_NOT_PROBED' for x in report['clis']))
        self.assertFalse(report['inference_executed'])
        self.assertFalse(report['authentication_checked'])

    def test_missing_clis_are_not_installed_or_started(self):
        with patch.object(worker.shutil, 'which', return_value=None), \
             patch.object(worker, 'capture') as capture:
            report = worker.diagnose(probe=True)
        capture.assert_not_called()
        self.assertTrue(all(x['status'] == 'NOT_INSTALLED' for x in report['clis']))

    def test_probe_only_uses_nine_allowlisted_information_commands(self):
        with patch.object(worker.shutil, 'which', side_effect=lambda name: '/installed/' + name), \
             patch.object(worker, 'capture', side_effect=fake_capture) as capture:
            report = worker.diagnose(probe=True)
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['subprocess_count'], 9)
        for call in capture.call_args_list:
            self.assertIn(call.args[0][1:], [['--version'], ['--help'], ['exec', '--help']])
            self.assertNotIn('API_KEY', call.args[2])
            self.assertEqual(call.args[2][worker.DEPTH_ENV], '1')
            self.assertLessEqual(call.args[3], 10)

    def test_first_failed_probe_stops_without_fallback(self):
        for failure in ['TIMEOUT', 'NONZERO_EXIT', 'OUTPUT_LIMIT', 'OS_ERROR']:
            with self.subTest(failure=failure), \
                 patch.object(worker.shutil, 'which', return_value='/installed/cli'), \
                 patch.object(worker, 'capture', return_value=({'status': failure}, b'')) as capture:
                report = worker.diagnose(probe=True)
            self.assertEqual(capture.call_count, 1)
            self.assertEqual(report['status'], 'STOPPED_ON_ERROR')
            self.assertFalse(report['inference_executed'])

    def test_recursion_is_blocked_before_discovery(self):
        for depth in ['1', '2', '-1', 'secret-string']:
            with self.subTest(depth=depth), patch.dict(os.environ, {worker.DEPTH_ENV: depth}), \
                 patch.object(worker.shutil, 'which') as which, patch.object(worker, 'capture') as capture:
                report = worker.diagnose(probe=True)
            self.assertEqual(report['status'], 'BLOCKED_RECURSION')
            which.assert_not_called()
            capture.assert_not_called()
            self.assertNotIn('secret-string', json.dumps(report))

    def test_total_budget_stops_before_launch(self):
        with patch.object(worker.shutil, 'which', return_value='/installed/cli'), \
             patch.object(worker.time, 'monotonic', side_effect=[0, 46]), \
             patch.object(worker, 'capture') as capture:
            report = worker.diagnose(probe=True)
        capture.assert_not_called()
        self.assertEqual(report['status'], 'STOPPED_ON_ERROR')
        self.assertEqual(report['subprocess_count'], 0)

    def test_secret_output_and_environment_are_not_in_report(self):
        secret = 'MOCK_SECRET_DO_NOT_LOG'
        def capture(argv, cwd, env, seconds):
            self.assertNotIn('OPENAI_API_KEY', env)
            self.assertNotIn('ANTHROPIC_API_KEY', env)
            self.assertNotIn('GITHUB_TOKEN', env)
            text = b'1.2.3 ' if argv[-1] == '--version' else b'--help --api-key '
            return {'status': 'PASS'}, text + secret.encode()
        with patch.dict(os.environ, {'OPENAI_API_KEY': secret, 'ANTHROPIC_API_KEY': secret, 'GITHUB_TOKEN': secret}), \
             patch.object(worker.shutil, 'which', return_value='/installed/cli'), \
             patch.object(worker, 'capture', side_effect=capture):
            report = worker.diagnose(probe=True)
        self.assertEqual(report['status'], 'PASS')
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn('--api-key', json.dumps(report))

    def test_unknown_version_or_help_is_not_verified(self):
        for raw in [b'', b'Please log in', b'credential=MOCK_SECRET']:
            with self.subTest(raw=raw), patch.object(worker.shutil, 'which', return_value='/installed/cli'), \
                 patch.object(worker, 'capture', return_value=({'status': 'PASS'}, raw)) as capture:
                report = worker.diagnose(probe=True)
            self.assertEqual(capture.call_count, 1)
            self.assertEqual(report['status'], 'STOPPED_ON_ERROR')
            self.assertNotIn('MOCK_SECRET', json.dumps(report))

    def test_worker_ok_plan_never_executes_inference(self):
        with patch.object(worker.shutil, 'which', return_value=None), patch.object(worker, 'capture') as capture:
            report = worker.diagnose(plan_cli='agy')
        capture.assert_not_called()
        self.assertEqual(report['worker_ok'], 'NOT_RUN')
        self.assertTrue(report['worker_ok_plan']['requires_explicit_local_approval'])
        self.assertFalse(report['worker_ok_plan']['ci_execution_allowed'])
        self.assertEqual(report['worker_ok_plan']['status'], 'PREPARED_NOT_EXECUTED')

    def test_arbitrary_worker_command_is_rejected(self):
        with self.assertRaises(ValueError):
            worker.diagnose(plan_cli='sh -c bad')

    def test_unknown_or_execution_flags_never_echo_secret_values(self):
        with patch.object(worker, 'diagnose') as diagnose, redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit):
                worker.main(['--run-worker-ok', '--api-key', 'MOCK_SECRET_DO_NOT_LOG'])
        diagnose.assert_not_called()
        self.assertNotIn('MOCK_SECRET', stderr.getvalue())

    def test_observed_options_use_exact_names(self):
        row = worker.summarize(b'--mode-extra --trust-me --sandbox', False)
        self.assertEqual(row['observed_options'], ['--sandbox'])

    def test_ci_discovery_does_not_require_credentials(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True), \
             patch.object(worker.shutil, 'which', return_value=None), patch.object(worker, 'capture') as capture, \
             redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(worker.main([]), 0)
        capture.assert_not_called()
        self.assertFalse(json.loads(stdout.getvalue())['authentication_checked'])

    def test_output_cannot_escape_reports_or_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fake_script = root / 'scripts/ci/check_worker_cli.py'
            (root / 'reports').mkdir()
            target = root / 'reports/existing.json'
            target.write_text('keep')
            (root / 'reports/link').symlink_to(root / 'outside', target_is_directory=True)
            for output in ['/tmp/forbidden.json', '../forbidden.json', 'data/raw/file.json',
                           'reports/../file.json', 'reports/existing.json', 'reports/link/file.json']:
                with self.subTest(output=output), patch.object(worker, '__file__', str(fake_script)), \
                     patch.object(worker, 'diagnose') as diagnose, redirect_stdout(io.StringIO()), \
                     redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        worker.main(['--output', output])
                    diagnose.assert_not_called()
            self.assertEqual(target.read_text(), 'keep')


# These subprocesses are Python fixtures only, never any installed AI CLI.
from contextlib import redirect_stderr


@unittest.skipUnless(os.name == 'posix', 'POSIX process groups required')
class CaptureTests(unittest.TestCase):
    def test_successful_capture_has_bounded_metadata(self):
        with tempfile.TemporaryDirectory() as cwd:
            result, raw = worker.capture([sys.executable, '-c', 'print("fixture")'], cwd, dict(os.environ), 2)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(raw, b'fixture\n')
        self.assertNotIn('fixture', json.dumps(result))

    def test_nonzero_exit_is_not_success(self):
        with tempfile.TemporaryDirectory() as cwd:
            result, _ = worker.capture([sys.executable, '-c', 'raise SystemExit(3)'], cwd, dict(os.environ), 2)
        self.assertEqual(result['status'], 'NONZERO_EXIT')
        self.assertEqual(result['exit_code'], 3)

    def test_oversized_output_is_stopped(self):
        with tempfile.TemporaryDirectory() as cwd, patch.object(worker, 'MAX_OUTPUT_BYTES', 1024):
            result, raw = worker.capture([sys.executable, '-c', 'print("x"*2048)'], cwd, dict(os.environ), 2)
        self.assertEqual(result['status'], 'OUTPUT_LIMIT')
        self.assertLessEqual(len(raw), 1024)

    def test_timeout_kills_inherited_pipe_child(self):
        child = 'import time; time.sleep(30)'
        code = 'import subprocess,sys; subprocess.Popen([sys.executable,"-c",' + repr(child) + '])'
        start = time.monotonic()
        with tempfile.TemporaryDirectory() as cwd:
            result, _ = worker.capture([sys.executable, '-c', code], cwd, dict(os.environ), .15)
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertLess(time.monotonic() - start, 3)


if __name__ == '__main__':
    unittest.main()
