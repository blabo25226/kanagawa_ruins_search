#!/usr/bin/env python3
"""Offline CLI discovery; optional bounded --version/--help probes, never inference."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

CLIS = ('codex', 'claude', 'agent', 'agy')
MAX_PROCESSES = 9
MAX_OUTPUT_BYTES = 128 * 1024
PER_PROCESS_SECONDS = 10
TOTAL_SECONDS = 45
DEPTH_ENV = 'KANAGAWA_WORKER_CLI_DEPTH'
# Only these fixed names can enter logs; arbitrary help/stdout/stderr never does.
OPTIONS = ('--version', '--help', '--print', '--sandbox', '--mode', '--trust',
           '--permission-mode', '--tools', '--output-format', '--output-last-message')
PLANS = {
    'codex': ['codex', 'exec', '--sandbox', 'read-only'],
    'claude': ['claude', '-p', '--permission-mode', 'plan', '--tools', 'Read,Glob,Grep'],
    'agent': ['agent', '-p', '--mode=ask'],
    'agy': ['agy', '-p', '--mode', 'plan', '--sandbox'],
}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error echoes unknown arguments/values (possibly keys).
        self.exit(2, 'Invalid or unsafe diagnostic arguments; use --help.\n')


def stop_group(process):
    """End the whole probe process group, including inherited-pipe children."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def capture(argv, cwd, env, seconds):
    """Bound stdout+stderr in memory and time. POSIX only; no shell, prompt or stdin."""
    if os.name != 'posix':
        return dict(status='UNSUPPORTED_PLATFORM'), b''
    process = None
    data = bytearray()
    status = 'PASS'
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   cwd=cwd, env=env, start_new_session=True)
        deadline = time.monotonic() + seconds
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'TIMEOUT'
                    break
                for key, _ in selector.select(min(remaining, .1)):
                    block = os.read(key.fd, 4096)
                    if not block:
                        selector.unregister(key.fileobj)
                    elif len(data) + len(block) > MAX_OUTPUT_BYTES:
                        status = 'OUTPUT_LIMIT'
                        break
                    else:
                        data.extend(block)
                if status != 'PASS':
                    break
        if status == 'PASS':
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = 'TIMEOUT'
            else:
                try:
                    if process.wait(timeout=remaining) != 0:
                        status = 'NONZERO_EXIT'
                except subprocess.TimeoutExpired:
                    status = 'TIMEOUT'
        result = dict(status=status, exit_code=process.poll(),
                      captured_bytes=len(data), output_sha256=hashlib.sha256(data).hexdigest())
        return result, bytes(data)
    except OSError:
        # Exception strings may contain paths/arguments; do not persist them.
        return dict(status='OS_ERROR'), b''
    finally:
        if process is not None:
            stop_group(process)
            process.stdout.close()


def summarize(raw, is_version):
    text = raw.decode('utf-8', errors='replace')
    if is_version:
        match = re.search(r'\b\d{1,4}(?:\.\d{1,3}){1,3}\b', text)
        return {'version': match.group(0) if match else 'UNRECOGNIZED'}
    return {'observed_options': [flag for flag in OPTIONS
                                if re.search(r'(?<![\w-])' + re.escape(flag) + r'(?![\w-])', text)],
            'mode_values_mentioned': [value for value in ('plan', 'accept-edits', 'acceptEdits', 'ask')
                                      if re.search(r'\b' + re.escape(value) + r'\b', text)]}


def diagnose(*, probe=False, plan_cli=None):
    report = dict(schema_version=1, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  mode='HELP_VERSION_ONLY' if probe else 'DISCOVERY_ONLY',
                  inference_executed=False, authentication_checked=False,
                  worker_ok='NOT_RUN', subprocess_count=0, clis=[],
                  limits=dict(max_processes=MAX_PROCESSES, concurrency=1, retries=0,
                              per_process_seconds=PER_PROCESS_SECONDS,
                              total_seconds=TOTAL_SECONDS, max_output_bytes=MAX_OUTPUT_BYTES,
                              cleanup_seconds_per_process=2,
                              max_delegation_depth=1))
    # A child may not invoke this diagnostic to create grandchildren.
    if os.environ.get(DEPTH_ENV, '0') != '0':
        return dict(report, status='BLOCKED_RECURSION')
    if plan_cli is not None and plan_cli not in CLIS:
        raise ValueError('Unknown CLI')
    if plan_cli:
        report['worker_ok_plan'] = dict(
            cli=plan_cli, status='PREPARED_NOT_EXECUTED',
            requires_explicit_local_approval=True, requires_isolated_worktree=True,
            requires_os_and_network_isolation=True, ci_execution_allowed=False,
            candidate_argv=PLANS[plan_cli] + ['Reply with exactly: WORKER_OK'],
            capability='CANDIDATE_ONLY; check installed help; no authenticated executor provided')
    # No inherited API keys, tokens, arbitrary environment variables, or prompts.
    child_env = {key: os.environ[key] for key in
                 ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR',
                  'XDG_CONFIG_HOME', 'XDG_CACHE_HOME') if key in os.environ}
    child_env.update({DEPTH_ENV: '1', 'NO_COLOR': '1', 'TERM': 'dumb'})
    deadline = time.monotonic() + TOTAL_SECONDS
    with (tempfile.TemporaryDirectory(prefix='ruins-cli-help-') if probe else nullcontext(None)) as cwd:
        for name in CLIS:
            executable = shutil.which(name)
            row = dict(cli=name, status='NOT_INSTALLED' if executable is None
                       else 'DISCOVERED_NOT_PROBED', checks=[])
            report['clis'].append(row)
            if executable is None or not probe:
                continue
            commands = [('--version',), ('--help',)]
            if name == 'codex':
                commands.append(('exec', '--help'))
            for arguments in commands:
                seconds = min(PER_PROCESS_SECONDS, deadline - time.monotonic())
                if seconds <= 0 or report['subprocess_count'] >= MAX_PROCESSES:
                    row['status'] = 'BUDGET_EXHAUSTED'
                    return dict(report, status='STOPPED_ON_ERROR')
                report['subprocess_count'] += 1
                check, raw = capture([executable, *arguments], cwd, child_env, seconds)
                check['argv'] = [name, *arguments]
                # Never log raw help/version output, stderr, env, or auth state.
                if check['status'] == 'PASS':
                    check.update(summarize(raw, arguments == ('--version',)))
                    if arguments == ('--version',) and check['version'] == 'UNRECOGNIZED':
                        check['status'] = 'UNRECOGNIZED_VERSION'
                    elif arguments != ('--version',) and not check['observed_options']:
                        check['status'] = 'UNRECOGNIZED_HELP'
                row['checks'].append(check)
                if check['status'] != 'PASS':
                    row['status'] = check['status']
                    return dict(report, status='STOPPED_ON_ERROR')
            row['status'] = 'HELP_VERSION_VERIFIED'
    return dict(report, status='PASS')


def main(argv=None):
    parser = SafeParser(__doc__)
    parser.add_argument('--probe-installed', action='store_true',
                        help='Only fixed --version/--help commands; never a model request.')
    parser.add_argument('--plan-worker-ok', choices=CLIS,
                        help='Prepare a candidate manual job contract; DOES NOT execute it.')
    parser.add_argument('--output', help='New JSON report under local reports/; never raw CLI logs.')
    args = parser.parse_args(argv)
    target = None
    if args.output:
        # Avoid following caller-supplied symlinks/Drive paths for report writes.
        relative = Path(args.output)
        if relative.is_absolute() or '..' in relative.parts or relative.parts[:1] != ('reports',):
            parser.error('--output must be a new relative file under local reports/')
        base = Path(__file__).resolve().parents[2]
        target = base / relative
        if any(parent.is_symlink() for parent in [target, *target.parents] if parent != base.parent):
            parser.error('symlinked report paths are not allowed')
        if target.exists():
            parser.error('report already exists; choose a new name')
    report = diagnose(probe=args.probe_installed, plan_cli=args.plan_worker_ok)
    report['diagnostic_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as output:
            output.write(payload)
    print(payload, end='')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
