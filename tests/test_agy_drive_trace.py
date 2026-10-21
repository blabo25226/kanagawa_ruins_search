"""Synthetic trace fixtures only: no agy, auth, Drive, filesystem metadata or network."""
import json
import unittest
from scripts.summarize_agy_drive_trace import MAX_TRACE_BYTES, TARGET, summarize


def trace(*events):
    return b'\n'.join(json.dumps(x).encode() for x in events)


class TraceTests(unittest.TestCase):
    def test_known_runtime_warnings_are_recorded_without_suggesting_bypass(self):
        raw = (b'warning: --mode plan has no effect while slash command expansion is disabled.\n'
               b'jetski: headless mode cannot prompt for permission, so it was auto-denied. '
               b'Unsafe recommendation MOCK_SECRET_VALUE\n')
        result = summarize(raw, exit_code=0)
        self.assertTrue(result['plan_mode_disabled_warning'])
        self.assertFalse(result['requested_plan_mode_effective'])
        self.assertTrue(result['headless_permission_auto_denied'])
        self.assertNotIn('Unsafe recommendation', json.dumps(result))
        self.assertNotIn('MOCK_SECRET', json.dumps(result))

    def test_exit_zero_and_success_do_not_override_denied_action(self):
        result = summarize(trace({'event': 'result', 'result': {
            'status': 'SUCCESS', 'response': '', 'num_turns': 1,
            'denied_actions': [{'action': 'command', 'display_name': 'RunCommand'}]}}), exit_code=0)
        self.assertEqual(result['status'], 'D_FAILED_UNVERIFIED')
        self.assertEqual(result['denied_action_count'], 1)
        self.assertFalse(result['file_content_verified'])
        self.assertIsNone(result['independent_drive_access'])

    def test_natural_language_success_and_base64_are_not_evidence(self):
        result = summarize(trace({'result': {'status': 'SUCCESS',
            'response': 'I read Drive successfully: MOCK_SECRET / private coordinates / base64'}}), exit_code=0)
        self.assertFalse(result['file_content_verified'])
        self.assertFalse(result['can_resume_c1_full_run'])
        self.assertNotIn('MOCK_SECRET', json.dumps(result))
        self.assertNotIn('coordinates', json.dumps(result))

    def test_active_and_done_are_one_attempt_not_successful_read(self):
        step = {'step_index': 2, 'step_type': 'tool', 'tool_name': 'run_command',
                'tool_info': {'parameters': {'CommandLine': 'stat '+TARGET+'/raw/fgd/example.zip …'}}}
        result = summarize(trace({'step_update': dict(step, state='ACTIVE')},
                                 {'step_update': dict(step, state='DONE')}), exit_code=0)
        self.assertEqual(len(result['tool_attempts']), 1)
        self.assertTrue(result['tool_attempts'][0]['target_fuse_path_mentioned'])
        self.assertTrue(result['tool_attempts'][0]['command_truncated_in_trace'])
        self.assertEqual(result['status'], 'D_FAILED_UNVERIFIED')

    def test_private_parameters_and_unknown_tools_are_not_logged(self):
        raw = trace({'init': {'tools': ['run_command', 'browser_get_dom', 'MOCK_SECRET_TOOL'],
                             'permission_mode': 'request-review'}},
                    {'step_update': {'step_type': 'tool', 'step_index': 0, 'tool_name': 'MOCK_SECRET_TOOL',
                                     'tool_info': {'parameters': {'secret': 'MOCK_SECRET_VALUE'}}}})
        result = summarize(raw, exit_code=1)
        self.assertNotIn('MOCK_SECRET', json.dumps(result))
        self.assertTrue(result['browser_tools_exposed'])
        self.assertEqual(result['runtime_permission_mode'], 'request-review')
        self.assertEqual(result['filesystem_tools_exposed'], ['run_command'])

    def test_missing_or_malformed_trace_is_unverified(self):
        result = summarize(b'not-json\n[]\n', exit_code=1)
        self.assertEqual(result['non_json_lines'], 2)
        self.assertFalse(result['file_content_verified'])
        self.assertEqual(result['runtime_result_status'], 'MISSING')

    def test_input_limit_prevents_unbounded_trace_expansion(self):
        with self.assertRaises(ValueError):
            summarize(b'x'*(MAX_TRACE_BYTES+1), exit_code=0)


if __name__ == '__main__':
    unittest.main()
