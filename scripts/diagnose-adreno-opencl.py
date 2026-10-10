#!/usr/bin/env python3
"""Compare OpenCL loader paths and capture each probe's own native errors; never install drivers."""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('opencl_probe', ROOT / 'scripts/probe-opencl.py')
opencl_probe = module_from_spec(spec)
spec.loader.exec_module(opencl_probe)
DRIVER_FILES = ('libOpenCL.so', 'libOpenCL_adreno.so', 'libOpenCL_Adreno.so', 'libCB.so',
                'libadreno_utils.so', 'libllvm-qcom.so', 'libllvm-glnext.so')
LIMIT = 8192


def capture(command, env, timeout):
    """Drain both pipes continuously, retaining only their last 8 KiB in memory."""
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    counts = {'stdout': 0, 'stderr': 0}
    deadline = time.monotonic() + timeout
    exited_at = None
    timed_out = False

    def stop_group():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    try:
        with selectors.DefaultSelector() as selector:
            for label, pipe in (('stdout', process.stdout), ('stderr', process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, label)
            while process.poll() is None or selector.get_map():
                now = time.monotonic()
                if process.poll() is None and now >= deadline:
                    timed_out = True
                    stop_group()
                    process.wait()
                if process.poll() is not None:
                    if exited_at is None:
                        exited_at = now
                    elif now - exited_at >= 1:
                        # A driver helper holding a pipe must not outlive this probe.
                        stop_group()
                        break
                for key, _ in selector.select(timeout=0.1):
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    label = key.data
                    counts[label] += len(chunk)
                    buffers[label].extend(chunk)
                    del buffers[label][:-LIMIT]
            process.wait()
    finally:
        if process.poll() is None:
            stop_group()
            process.wait()
        process.stdout.close()
        process.stderr.close()
    result = {'pid': process.pid, 'exit_code': process.returncode, 'timed_out': timed_out}
    for label, buffer in buffers.items():
        prefix = '[earlier output truncated]\n' if counts[label] > LIMIT else ''
        result[label] = prefix + buffer.decode('utf-8', errors='replace')
    return result


def collect_logcat(pid, started):
    logcat = shutil.which('logcat')
    if not logcat:
        return {'status': 'unavailable', 'error': 'logcat is not on PATH.'}
    # No unfiltered fallback: read only this fresh probe PID, since its start time.
    command = [logcat, '-d', f'--pid={pid}', '-T', f'{int(started * 1000) / 1000:.3f}',
               '-v', 'brief', '*:V']
    env = os.environ.copy()
    env.pop('LD_LIBRARY_PATH', None)
    try:
        result = capture(command, env, 5)
        if result['timed_out']:
            return {'status': 'unavailable', 'error': 'PID-scoped logcat timed out.'}
        if result['exit_code']:
            return {'status': 'unavailable', 'error': result['stderr'] or
                    f"PID-scoped logcat exited {result['exit_code']}."}
        lines = []
        for line in result['stdout'].splitlines():
            match = re.match(r'^[VDIWEFA]/.+?\(\s*(\d+)\s*\):', line)
            if match and int(match.group(1)) == pid:
                lines.append(line)
        return {'status': 'collected' if lines else 'empty', 'text': '\n'.join(lines)}
    except OSError as error:
        return {'status': 'unavailable', 'error': str(error)}


def run_probe(library, env, timeout):
    with tempfile.TemporaryDirectory(prefix='spice-opencl-probe-') as directory:
        checkpoint = Path(directory) / 'result.json'
        started = time.time()
        result = capture([sys.executable, str(ROOT / 'scripts/probe-opencl.py'),
                          '--library', library, '--result-file', str(checkpoint)], env, timeout)
        try:
            report = json.loads(checkpoint.read_text())
        except (OSError, ValueError):
            report = {'library': library, 'ready': False, 'stage': 'child-start', 'platforms': []}
        report.update(pid=result['pid'], exit_code=result['exit_code'], timed_out=result['timed_out'],
                      native_stdout=result['stdout'], native_stderr=result['stderr'])
    if result['timed_out'] or result['exit_code'] != 0:
        report['ready'] = False
        if result['timed_out']:
            report['error'] = f'Native probe exceeded {timeout:g} seconds and was killed.'
        elif result['exit_code'] < 0:
            report['error'] = f"Native probe terminated by signal {-result['exit_code']}."
        elif 'error' not in report:
            report['error'] = f"Probe exited {result['exit_code']} before completing."
    report['android_logcat'] = collect_logcat(result['pid'], started) if not report['ready'] else {
        'status': 'not-collected', 'reason': 'GPU enumeration succeeded.'}
    return report


def inventory(vendor, prefix):
    files = []
    for name in DRIVER_FILES:
        path = vendor / name
        try:
            files.append({'path': str(path), 'bytes': path.stat().st_size})
        except OSError as error:
            files.append({'path': str(path), 'error': str(error)})
    directories = [Path('/vendor/Khronos/OpenCL/vendors'),
                   Path('/system/vendor/Khronos/OpenCL/vendors')]
    if prefix:
        directories.append(Path(prefix) / 'etc/OpenCL/vendors')
    icds = []
    for directory in directories:
        entry = {'directory': str(directory), 'files': []}
        try:
            for path in sorted(directory.glob('*.icd'))[:16]:
                with path.open('r', errors='replace') as file:
                    entry['files'].append({'path': str(path), 'content': file.read(4096).strip()})
            if not directory.is_dir():
                entry['error'] = 'Directory absent or inaccessible.'
        except OSError as error:
            entry['error'] = str(error)
        icds.append(entry)
    return files, icds


def compare(env, timeout):
    vendor = Path(env.get('SPICE_OPENCL_VENDOR_DIR', '/vendor/lib64'))
    prefix = env.get('PREFIX', '')
    files, icds = inventory(vendor, prefix)
    report = {'purpose': 'GPU enumeration and driver diagnostics; kernels/inference untested.',
              'vendor_files': files, 'icd_files': icds, 'copy_errors': [], 'probes': []}
    paths = [str(vendor), str(vendor / 'egl')]
    if prefix:
        paths.append(str(Path(prefix) / 'lib'))
    paths.append('/system/lib64')
    search = ':'.join(paths)
    if env.get('LD_LIBRARY_PATH'):
        search += ':' + env['LD_LIBRARY_PATH']
    with tempfile.TemporaryDirectory(prefix='spice-adreno-copy-') as directory:
        for name in DRIVER_FILES:
            source = vendor / name
            try:
                if source.is_file():
                    shutil.copy2(source, Path(directory) / name)
            except OSError as error:
                report['copy_errors'].append({'path': str(source), 'error': str(error)})
        copied = Path(directory) / 'libOpenCL.so'
        if copied.exists():
            (Path(directory) / 'libOpenCL.so.1').symlink_to('libOpenCL.so')
        isolated_paths = [directory]
        if prefix:
            isolated_paths.append(str(Path(prefix) / 'lib'))
        isolated_search = ':'.join(isolated_paths + [str(vendor), str(vendor / 'egl'), '/system/lib64'])
        if env.get('LD_LIBRARY_PATH'):
            isolated_search += ':' + env['LD_LIBRARY_PATH']
        candidates = [('packaged', 'libOpenCL.so', env.get('LD_LIBRARY_PATH', '')),
                      ('direct-vendor', str(vendor / 'libOpenCL.so'), search),
                      ('isolated-copy', str(copied), isolated_search)]
        for label, library, library_path in candidates:
            child_env = dict(env, LD_LIBRARY_PATH=library_path)
            probe = run_probe(library, child_env, timeout)
            probe['label'] = label
            probe['loader_environment'] = {key: child_env[key] for key in
                                          ('LD_LIBRARY_PATH', 'OCL_ICD_VENDORS', 'OCL_ICD_FILENAMES',
                                           'OPENCL_VENDOR_PATH') if key in child_env}
            report['probes'].append(probe)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', help='Probe one entry point instead of comparing all three.')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'runtime/adreno-opencl/diagnostic.json')
    parser.add_argument('--timeout', type=float, default=30, help='Per-probe timeout, at most 30 seconds.')
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error('--timeout must be greater than zero and at most 30 seconds.')
    report = run_probe(args.library, os.environ.copy(), args.timeout) if args.library else \
        compare(os.environ.copy(), args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    opencl_probe.save_report(args.output, report)
    print(json.dumps(report, indent=2))
    if not args.library:
        print(f'Saved diagnostic: {args.output.resolve()}', file=sys.stderr)
    ready = report['ready'] if args.library else any(p['ready'] for p in report['probes'])
    return 0 if ready else 1


if __name__ == '__main__':
    raise SystemExit(main())
