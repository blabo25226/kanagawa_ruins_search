"""Offline guards for Issue #12: selection, fail-fast, remote verification."""
from contextlib import nullcontext
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from kanagawa_ruins.temporal_pipeline import inventory, TemporalSettings
from kanagawa_ruins.storage.scratch import Scratch


def script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IngestReviewTests(unittest.TestCase):
    def test_inventory_excludes_deferred_raw_before_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for year in ['2008', '2014', '2025']:
                rows.append(dict(source_id=year, relative_path=f'raw/{year}.zip',
                                 sha256='0'*64, temporal_coverage=year, acquired_at=None,
                                 license=None, source_url=None, source_page=None, size_bytes=0))
            # Only the selected source exists. Deferred/unrequested paths must
            # never be verified, hashed, statted or opened.
            path = root / 'raw/2014.zip'
            path.parent.mkdir()
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('FG-GML-523867-ALL-20140101-Z001.zip', b'fixture')
            rows[1]['size_bytes'] = path.stat().st_size
            from kanagawa_ruins.qa.hashing import sha256
            rows[1]['sha256'] = sha256(path)
            with patch('kanagawa_ruins.temporal_pipeline.read_sources', return_value=[]), \
                 patch('kanagawa_ruins.temporal_pipeline.scratch_job', return_value=nullcontext(Scratch(root, 1000000))):
                items, _, sources = inventory(TemporalSettings(root), {'records': rows}, years={'2014'})
            self.assertEqual([x['era'] for x in items], ['2014'])
            self.assertEqual(list(sources), ['2014'])

    def run_ingest(self, root, extra=(), fail_on=None, resume=None):
        module = script('phase1c1_ingest')
        plan = root / 'plan.json'
        plan.write_text('{}')
        gate = root / 'pilot.json'
        gate.write_text(json.dumps({'status': 'PASS', 'errors': []}))
        output = root / 'output.json'
        settings = Mock(data_root=root)
        all_items = [dict(era=y, code='523867', source_id=y) for y in ['2008', '2014', '2025']]
        def selected_inventory(settings, plan, *, years):
            return [x for x in all_items if x['era'] in years], [], {y: y for y in years}
        def convert(settings, item, source, **kwargs):
            if item['era'] == fail_on:
                raise OSError('HTTP 403 RATE_LIMIT_EXCEEDED')
            return dict(**item, layers=[], counts={}, excluded_invalid={})
        cli = ['--plan', str(plan), '--report', str(output), '--pilot-report', str(gate), *extra]
        if resume is not None:
            previous = root / 'previous.json'
            previous.write_text(json.dumps({'results': resume}))
            cli += ['--resume-report', str(previous)]
        with patch.object(module.TemporalSettings, 'from_env', return_value=settings), \
             patch.object(module, 'inventory', side_effect=selected_inventory) as inv, \
             patch.object(module, 'ingest_item', side_effect=convert) as ingest, \
             patch.object(module, 'load_layer') as load, \
             patch.object(module, 'sha256', side_effect=AssertionError('Unselected resume accessed remote')):
            rc = module.main(cli)
        return rc, json.loads(output.read_text()), inv, ingest, load

    def test_default_all_selects_only_2014_2025(self):
        with tempfile.TemporaryDirectory() as d:
            rc, report, inv, ingest, _ = self.run_ingest(Path(d), ['--stage', 'all'])
        self.assertEqual(rc, 0)
        self.assertEqual(report['years'], ['2014', '2025'])
        self.assertEqual([c.args[1]['era'] for c in ingest.call_args_list], ['2014', '2025'])
        self.assertEqual(inv.call_args.kwargs['years'], {'2014', '2025'})
        self.assertTrue(all(c.kwargs['kinds'] == {'BldA', 'RdEdg'} for c in ingest.call_args_list))

    def test_explicit_year_filter(self):
        with tempfile.TemporaryDirectory() as d:
            rc, report, _, ingest, _ = self.run_ingest(Path(d), ['--years', '2025'])
        self.assertEqual(rc, 0)
        self.assertEqual([c.args[1]['era'] for c in ingest.call_args_list], ['2025'])

    def test_first_remote_failure_stops_without_next_partition(self):
        with tempfile.TemporaryDirectory() as d:
            rc, report, _, ingest, _ = self.run_ingest(Path(d), ['--stage', 'all'], fail_on='2014')
        self.assertEqual(rc, 1)
        self.assertEqual(ingest.call_count, 1)
        self.assertEqual(report['status'], 'STOPPED_ON_ERROR')
        self.assertEqual(len(report['errors']), 1)
        self.assertEqual(report['results'], [])

    def test_failure_keeps_completed_partition_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            rc, report, _, ingest, _ = self.run_ingest(Path(d), ['--stage', 'all'], fail_on='2025')
        self.assertEqual(rc, 1)
        self.assertEqual(ingest.call_count, 2)
        self.assertEqual([r['era'] for r in report['results']], ['2014'])
        self.assertEqual(report['status'], 'STOPPED_ON_ERROR')

    def test_resume_does_not_read_deferred_2008_outputs(self):
        previous = [dict(era='2008', code='14101', layers=[{'processed_path': 'must_not_open'}])]
        with tempfile.TemporaryDirectory() as d:
            rc, report, _, _, _ = self.run_ingest(Path(d), ['--stage', 'all'], resume=previous)
        self.assertEqual(rc, 0)
        self.assertEqual(report['resume_ignored_partitions'], [{'era': '2008', 'code': '14101'}])
        self.assertEqual([r['era'] for r in report['results']], ['2014', '2025'])

    def test_invalid_year_rejected_before_any_mount_access(self):
        module = script('phase1c1_ingest')
        with patch.object(module.TemporalSettings, 'from_env') as settings:
            with self.assertRaises(SystemExit):
                module.main(['--years', '2015', '--report', 'unused.json'])
            settings.assert_not_called()


class RemoteReviewTests(unittest.TestCase):
    def test_remote_stream_hashes_without_retaining_vector(self):
        module = script('phase1c1_verify_remote')
        process = Mock(stdout=io.BytesIO(b'actual remote bytes'))
        process.wait.return_value = 0
        process.poll.return_value = 0
        with patch.object(module.subprocess, 'Popen', return_value=process) as popen:
            digest, content = module.remote_read('processed/vector.parquet', 'fixture', 100)
        self.assertEqual(digest, {'sha256': hashlib.sha256(b'actual remote bytes').hexdigest(), 'bytes': 19})
        self.assertEqual(content, b'')
        cmd = popen.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--low-level-retries') + 1], '1')

    def test_remote_oversize_is_rejected(self):
        module = script('phase1c1_verify_remote')
        process = Mock(stdout=io.BytesIO(b'oversize'))
        process.poll.return_value = 0
        with patch.object(module.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(ValueError, 'exceeds'):
                module.remote_read('processed/vector.parquet', 'fixture', 2)

    def test_remote_error_rejects_even_matching_partial_bytes(self):
        module = script('phase1c1_verify_remote')
        process = Mock(stdout=io.BytesIO(b'partial'))
        process.wait.return_value = 1
        process.poll.return_value = 1
        with patch.object(module.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(OSError, 'exit 1'):
                module.remote_read('processed/vector.parquet', 'fixture', 100)

    def test_remote_verifier_stops_at_first_failure(self):
        module = script('phase1c1_verify_remote')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'ingest.json'
            source.write_text(json.dumps({'results': [{'layers': [dict(layer_id=f'layer{i}', processed_path=f'path{i}', bytes=1) for i in range(9)]}]}))
            output = root / 'output.json'
            with patch('sys.argv', ['verify', '--root-id', 'fixture', '--ingest-report', str(source), '--report', str(output)]), \
                 patch.object(module, 'remote_read', side_effect=OSError('403 RATE_LIMIT_EXCEEDED')) as read:
                self.assertEqual(module.main(), 1)
            self.assertEqual(read.call_count, 1)
            report = json.loads(output.read_text())
            self.assertFalse(report['remote_upload_verified'])
            self.assertEqual(report['status'], 'STOPPED_ON_ERROR')

    def test_manifest_mismatch_is_not_verified(self):
        module = script('phase1c1_verify_remote')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            layer = dict(layer_id='first', processed_path='first.parquet', bytes=1, output_sha256='0'*64)
            source = root / 'ingest.json'
            source.write_text(json.dumps({'results': [{'layers': [dict(layer, layer_id=f'layer{i}') for i in range(9)]}]}))
            output = root / 'output.json'
            reads = [({'bytes': 1, 'sha256': '0'*64}, b''), ({}, b'{"layer_id":"wrong"}')]
            with patch('sys.argv', ['verify', '--root-id', 'fixture', '--ingest-report', str(source), '--report', str(output)]), \
                 patch.object(module, 'remote_read', side_effect=reads) as read:
                self.assertEqual(module.main(), 1)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(json.loads(output.read_text())['results'], [])
