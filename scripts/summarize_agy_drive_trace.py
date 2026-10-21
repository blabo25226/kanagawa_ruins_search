#!/usr/bin/env python3
"""Offline-only evidence summary. Never launches agy or reads Google Drive."""
import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_TRACE_BYTES = 524288
TARGET = '/home/blabo/gdrive/kanagawa_ruins_search_databank/data'
MANIFEST = TARGET + '/processed/phase1c/codex/manifests/fgd__2008_14101__blda_v1.json'
SAFE_TOOLS = {'run_command', 'view_file', 'read_file', 'list_dir', 'list_directory'}


def summarize(raw, *, exit_code):
    if len(raw) > MAX_TRACE_BYTES:
        raise ValueError('Trace admission ceiling exceeded')
    events = []
    # Fixed diagnostic booleans only; never echo arbitrary warning text.
    mode_warning = b'--mode plan has no effect while slash command expansion is disabled' in raw
    headless_denial = b'headless mode cannot prompt for' in raw and b'auto-denied' in raw
    invalid_lines = 0
    for line in raw.splitlines():
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('not an object')
            events.append(value)
        except ValueError:
            invalid_lines += 1
    tools, steps, denied = [], {}, 0
    permission_mode, result_status = 'UNKNOWN', 'MISSING'
    num_turns = None
    response_nonempty = False
    for event in events:
        init = event.get('init', {})
        if isinstance(init, dict):
            tools += [t for t in init.get('tools', []) if isinstance(t, str)]
            value = init.get('permission_mode')
            if value in {'request-review', 'plan', 'accept-edits'}:
                permission_mode = value
        step = event.get('step_update', {})
        if isinstance(step, dict) and step.get('step_type') == 'tool':
            info = step.get('tool_info', {})
            params = info.get('parameters', {}) if isinstance(info, dict) else {}
            encoded = json.dumps(params, sort_keys=True).encode()
            command = params.get('CommandLine', '') if isinstance(params, dict) else ''
            name = step.get('tool_name')
            index = step.get('step_index')
            # Public fixed labels and digests only. No raw commands/contents.
            steps[index if isinstance(index, int) else len(steps)] = {
                'tool_name': name if name in SAFE_TOOLS else 'OTHER_TOOL',
                'parameters_sha256': hashlib.sha256(encoded).hexdigest(),
                'target_fuse_path_mentioned': TARGET in encoded.decode(),
                'command_truncated_in_trace': isinstance(command, str) and '…' in command,
            }
        result = event.get('result', {})
        if isinstance(result, dict) and result:
            status = result.get('status')
            result_status = status if status in {'SUCCESS', 'ERROR', 'FAILED', 'CANCELLED'} else 'OTHER'
            actions = result.get('denied_actions', [])
            denied += len(actions) if isinstance(actions, list) else 0
            turns = result.get('num_turns')
            if type(turns) is int:
                num_turns = turns
            response_nonempty = bool(result.get('response'))
    # Neither a model claim, a tool's DONE state nor exit 0 proves a file read.
    return dict(trace_sha256=hashlib.sha256(raw).hexdigest(), trace_bytes=len(raw),
                json_events=len(events), non_json_lines=invalid_lines,
                exit_code=exit_code, runtime_result_status=result_status,
                num_turns=num_turns, runtime_permission_mode=permission_mode,
                plan_mode_disabled_warning=mode_warning,
                requested_plan_mode_effective=False if mode_warning else None,
                headless_permission_auto_denied=headless_denial,
                filesystem_tools_exposed=sorted(set(tools) & SAFE_TOOLS),
                browser_tools_exposed=any(t.startswith('browser_') for t in tools),
                dedicated_drive_name_in_tool_inventory=any('drive' in t.lower() for t in tools),
                tool_attempts=list(steps.values()), denied_action_count=denied,
                final_response_nonempty=response_nonempty,
                status='D_FAILED_UNVERIFIED', independent_drive_access=None,
                file_content_verified=False, large_binary_transfer_verified=False,
                can_resume_c1_full_run=False,
                classifier_scope='Evidence-only: this summary never promotes unverified claims to A/B/C')


def result_payload(response):
    """Parse one final object; never treat model assertions as access evidence."""
    if not isinstance(response, str):
        return {}
    try:
        value = json.loads(response)
    except ValueError:
        blocks = re.findall(r'```json\s*(.*?)```', response, re.DOTALL)
        if len(blocks) != 1:
            return {}
        try:
            value = json.loads(blocks[0])
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def verify_manifest(raw, *, exit_code, expected_bytes, expected_sha256):
    """Bind returned bytes to the actual native read and a trusted reference SHA.

    This verifies only the known FUSE file, never independent remote upload.
    The summary alone remains conservative; this explicit check may promote C.
    """
    evidence = summarize(raw, exit_code=exit_code)
    native_read, native_size = False, None
    payload = {}
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        step = event.get('step_update', {})
        if isinstance(step, dict) and step.get('state') == 'DONE' and step.get('tool_name') in {'read_file', 'view_file'}:
            info = step.get('tool_info', {})
            params = info.get('parameters', {}) if isinstance(info, dict) else {}
            if isinstance(params, dict) and params.get('Path') == MANIFEST:
                native_read = True
                output = info.get('output')
                match = re.fullmatch(r'\s*\d+\s+lines,?\s+(\d+)\s+bytes\.?\s*', output) if isinstance(output, str) else None
                if match:
                    native_size = int(match.group(1))
        result = event.get('result', {})
        if isinstance(result, dict) and result:
            payload = result_payload(result.get('response'))
    text = payload.get('manifest_text')
    content = text.encode('utf-8') if isinstance(text, str) and len(text) <= 8192 else None
    digest = hashlib.sha256(content).hexdigest() if content is not None else None
    verified = (exit_code == 0 and evidence['runtime_result_status'] == 'SUCCESS'
                and evidence['denied_action_count'] == 0 and native_read
                and native_size == expected_bytes and content is not None
                and len(content) == expected_bytes and digest == expected_sha256)
    return dict(evidence, status='C_SAME_RCLONE_PATH_CONTENT_VERIFIED' if verified else 'D_FAILED_UNVERIFIED',
                independent_drive_access=False if verified else None,
                file_content_verified=verified, native_read_target_observed=native_read,
                native_read_size_bytes=native_size,
                returned_content_bytes=len(content) if content is not None else None,
                returned_content_sha256=digest, reference_size_bytes=expected_bytes,
                reference_sha256=expected_sha256,
                classifier_scope='C requires native read evidence, no denial, exact byte count and trusted reference SHA; no A/B claims')


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--private-trace', required=True)
    parser.add_argument('--exit-code', type=int, required=True)
    args = parser.parse_args(argv)
    with Path(args.private_trace).open('rb') as source:
        raw = source.read(MAX_TRACE_BYTES + 1)
    print(json.dumps(summarize(raw, exit_code=args.exit_code), indent=2))


if __name__ == '__main__':
    main()
