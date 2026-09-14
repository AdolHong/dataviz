"""Bound a pytest lane without trusting a responsive Playwright driver."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import psutil


def run_supervised(command, *, cwd, env, log, progress, timeout):
    env = {**env, 'DATAVIZ_E2E_PROGRESS': str(progress),
           'DATAVIZ_E2E_PHASE_TIMEOUT': str(timeout), 'PYTHONUNBUFFERED': '1'}
    env.pop('DATAVIZ_E2E_WATCHDOG_OWNER', None)
    process = None
    descendants = set()
    phase = {}
    last_change = time.monotonic()
    signature = None
    timed_out = False
    try:
        with Path(log).open('x') as stream:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=os.name == 'posix')
            while process.poll() is None:
                try:
                    descendants.update(psutil.Process(process.pid).children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
                try:
                    content = Path(progress).read_text()
                    current = json.loads(content)
                    if current.get('pid') == process.pid and content != signature:
                        signature, phase = content, current
                        last_change = time.monotonic()
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                # The in-process watchdog dumps Python stacks first. This
                # independent deadline also covers collection/driver shutdown.
                if time.monotonic() - last_change > timeout + 5:
                    timed_out = True
                    print(f'WATCHDOG: no phase completion: {phase or "startup"}', file=stream, flush=True)
                    break
                time.sleep(0.1)
            if not timed_out:
                timed_out = bool(phase.get('phase') in {'setup', 'call', 'teardown', 'collection', 'sessionfinish'}
                                 and process.returncode == 1
                                 and Path(progress).with_suffix('.stacks.log').exists()
                                 and 'Timeout (' in Path(progress).with_suffix('.stacks.log').read_text())
    finally:
        if process is not None:
            # Own process group only: browser/driver children must not outlive
            # their pytest lane, even if pytest exited via faulthandler._exit.
            if os.name == 'posix':
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        break
                    except PermissionError:
                        # Some execution hosts disallow group signals even
                        # for a newly-created session. Fall back to identities
                        # captured while pytest still owned its descendants.
                        break
                    if sig == signal.SIGTERM:
                        time.sleep(0.2)
            for child in descendants:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
    return {'exit_code': 124 if timed_out else process.returncode,
            'timed_out': timed_out, 'last_phase': phase}
