import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <signal.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/resource.h>
typedef void * id;
int clGetPlatformIDs(unsigned n, id *out, unsigned *count) {
#ifdef NATIVE_ERROR
    fputs("fixture: native driver initialization failed\n", stderr);
    fputs("fixture: native stdout is not JSON\n", stdout);
    fflush(stdout);
#endif
#ifdef NOISY
    for (int i = 0; i < 20000; i++) fputs("driver diagnostic noise\n", stderr);
    fputs("final driver error\n", stderr);
#endif
#ifdef LIMITED_FLOOD
    struct rlimit output_limit = {32768, 32768};
    setrlimit(RLIMIT_FSIZE, &output_limit);
    char block[4096];
    memset(block, 'x', sizeof(block));
    for (int i = 0; i < 4096; i++) fwrite(block, 1, sizeof(block), stderr);
    fputs("\nfinal driver error\n", stderr);
#endif
#ifdef HANG
    sleep(60);
#endif
#ifdef CRASH
    raise(SIGABRT);
#endif
#ifdef NO_PLATFORM
    if (count) *count = 0;
    return -1001;
#else
    if (count) *count = 1;
    if (out && n) out[0] = (id) 1;
    return 0;
#endif
}
int info(const char *text, size_t n, void *out, size_t *size) {
    size_t len = strlen(text) + 1;
    if (size) *size = len;
    if (out && n >= len) memcpy(out, text, len);
    return 0;
}
int clGetPlatformInfo(id p, unsigned key, size_t n, void *out, size_t *size) {
    return info(key == 0x0903 ? "Qualcomm" : "Qualcomm OpenCL", n, out, size);
}
int clGetDeviceIDs(id p, uint64_t type, unsigned n, id *out, unsigned *count) {
#ifdef NO_GPU
    if (count) *count = 0;
    return -1;
#else
    if (type != 4) return -30;
    if (count) *count = 1;
    if (out && n) out[0] = (id) 2;
    return 0;
#endif
}
int clGetDeviceInfo(id d, unsigned key, size_t n, void *out, size_t *size) {
    return info(key == 0x102D ? "fixture-driver" : "Adreno (TM) 750", n, out, size);
}
'''


@unittest.skipUnless(shutil.which('cc'), 'Native OpenCL ABI fixtures need a C compiler')
class AdrenoOpenCLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vendor = self.root / 'vendor'
        self.vendor.mkdir()
        self.prefix = self.root / 'termux'
        (self.prefix / 'lib').mkdir(parents=True)
        (self.root / 'scripts').mkdir()
        for name in ('setup-adreno-opencl.sh', 'probe-opencl.py', 'diagnose-adreno-opencl.py'):
            path = ROOT / 'scripts' / name
            if path.exists():
                shutil.copy2(path, self.root / 'scripts')
        self.source = self.root / 'driver.c'
        self.source.write_text(DRIVER)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(('SPICE_LLM_', 'SPICE_OPENCL_', 'OCL_ICD_'))}
        self.env.update(PREFIX=str(self.prefix), PYTHON_BIN=sys.executable,
                        SPICE_OPENCL_VENDOR_DIR=str(self.vendor))

    def build_driver(self, *options):
        path = self.vendor / 'libOpenCL.so'
        subprocess.run(['cc', '-shared', '-fPIC', *options, str(self.source), '-o', str(path)],
                       check=True, capture_output=True)
        return path

    def probe(self, library):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/probe-opencl.py'),
                                 '--library', str(library)], text=True,
                                capture_output=True, timeout=10)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result, json.loads(result.stdout)

    def install(self):
        return subprocess.run(['bash', 'scripts/setup-adreno-opencl.sh'], cwd=self.root,
                              env=self.env, text=True, capture_output=True, timeout=15)

    def diagnose(self, *args):
        script = self.root / 'scripts/diagnose-adreno-opencl.py'
        self.assertTrue(script.exists(), 'The driver evidence collector is missing')
        output = self.root / 'diagnostic.json'
        result = subprocess.run([sys.executable, str(script), '--output', str(output), *args],
                                env=self.env, cwd=self.root, text=True,
                                capture_output=True, timeout=15)
        self.assertTrue(output.exists(), result.stdout + result.stderr)
        return result, json.loads(output.read_text())

    def test_probe_identifies_the_library_owning_the_api_symbol(self):
        library = self.build_driver('-DNO_PLATFORM')
        result, report = self.probe(library)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('api_library'), str(library.resolve()))
        self.assertIn(str(library.resolve()), report.get('loaded_driver_libraries', []))
        self.assertEqual(report.get('error_name'), 'CL_PLATFORM_NOT_FOUND_KHR')
        self.assertGreater(report.get('pid', 0), 0)

    def test_failed_setup_preserves_native_evidence_after_stage_cleanup(self):
        self.build_driver('-DNO_PLATFORM', '-DNATIVE_ERROR')
        result = self.install()
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        output = self.root / 'runtime/adreno-opencl/last-setup-failure.json'
        self.assertTrue(output.exists(), 'Failed setup discards its only driver evidence')
        report = json.loads(output.read_text())
        self.assertEqual(report['code'], -1001)
        self.assertIn('native driver initialization failed', report['native_stderr'])
        self.assertIn('native stdout is not JSON', report['native_stdout'])
        self.assertFalse(list((self.root / 'runtime/adreno-opencl').glob('.stage.*')))

    def test_comparison_isolates_packaged_vendor_and_copied_entrypoints(self):
        driver = self.build_driver('-DNO_PLATFORM')
        packaged = self.prefix / 'lib/libOpenCL.so'
        shutil.copy2(driver, packaged)
        self.build_driver()
        self.env['LD_LIBRARY_PATH'] = str(self.prefix / 'lib')
        icd_dir = self.prefix / 'etc/OpenCL/vendors'
        icd_dir.mkdir(parents=True)
        (icd_dir / 'vendor.icd').write_text(str(driver) + '\n')
        self.env['SPICE_ANDROID_VOICE_TOKEN'] = 'private-token-must-not-be-in-report'
        (self.root / '.env.s24').write_text('MODEL_SECRET=private-file-must-not-be-read\n')
        snapshots = {path: path.read_bytes() for path in (driver, packaged)}
        result, report = self.diagnose()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        probes = report['probes']
        self.assertEqual([p['label'] for p in probes], ['packaged', 'direct-vendor', 'isolated-copy'])
        self.assertEqual([p['ready'] for p in probes], [False, True, True])
        self.assertEqual(probes[0]['api_library'], str(packaged.resolve()))
        self.assertEqual(probes[1]['api_library'], str(driver.resolve()))
        self.assertEqual(len({p['pid'] for p in probes}), 3)
        self.assertIn('vendor.icd', json.dumps(report['icd_files']))
        self.assertNotIn('private-token-must-not-be-in-report', json.dumps(report))
        self.assertNotIn('private-file-must-not-be-read', json.dumps(report))
        self.assertFalse((self.root / 'runtime/adreno-opencl/current').exists())
        for path, expected in snapshots.items():
            self.assertEqual(path.read_bytes(), expected)

    def test_native_abort_keeps_pid_and_checkpoint(self):
        library = self.build_driver('-DCRASH', '-DNATIVE_ERROR')
        result, report = self.diagnose('--library', str(library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report['stage'], 'platforms')
        self.assertEqual(report['api_library'], str(library.resolve()))
        self.assertLess(report['exit_code'], 0)
        self.assertIn('native driver initialization failed', report['native_stderr'])
        self.assertGreater(report['pid'], 0)

    def test_hanging_native_call_is_killed_and_preserves_checkpoint(self):
        library = self.build_driver('-DHANG')
        result, report = self.diagnose('--library', str(library), '--timeout', '0.2')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(report['timed_out'])
        self.assertEqual(report['stage'], 'platforms')
        self.assertEqual(report['api_library'], str(library.resolve()))
        self.assertFalse(report['ready'])

    def fake_logcat(self, body):
        directory = self.root / 'bin'
        directory.mkdir()
        path = directory / 'logcat'
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o755)
        self.env['PATH'] = str(directory) + os.pathsep + self.env.get('PATH', '')

    def test_logcat_collects_only_the_failed_probe_pid(self):
        library = self.build_driver('-DNO_PLATFORM')
        self.fake_logcat('import sys\n'
                        'pid = next(arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--pid="))\n'
                        'print(f"E/Adreno-CB( {pid}): fixture driver error")\n'
                        'print(f"E/OtherApp( {int(pid) + 1}): unrelated private log")\n')
        result, report = self.diagnose('--library', str(library))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['android_logcat']['status'], 'collected')
        self.assertIn('fixture driver error', report['android_logcat']['text'])
        self.assertNotIn('unrelated private log', json.dumps(report))

    def test_unsupported_pid_filter_does_not_retry_unfiltered_logcat(self):
        library = self.build_driver('-DNO_PLATFORM')
        calls = self.root / 'logcat-calls'
        self.fake_logcat('import sys\nfrom pathlib import Path\n'
                        f'with Path({str(calls)!r}).open("a") as f: f.write("called\\n")\n'
                        'print("unsupported --pid option", file=sys.stderr)\n'
                        'raise SystemExit(1)\n')
        result, report = self.diagnose('--library', str(library))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['android_logcat']['status'], 'unavailable')
        self.assertIn('unsupported --pid', report['android_logcat']['error'])
        self.assertEqual(calls.read_text(), 'called\n')

    def test_large_native_output_is_bounded_but_preserves_the_error_tail(self):
        library = self.build_driver('-DNO_PLATFORM', '-DNOISY')
        result, report = self.diagnose('--library', str(library))
        self.assertEqual(result.returncode, 1)
        self.assertLess(len(report['native_stderr']), 8300)
        self.assertIn('[earlier output truncated]', report['native_stderr'])
        self.assertIn('final driver error', report['native_stderr'])

    def test_capture_does_not_write_unbounded_native_temporary_files(self):
        library = self.build_driver('-DNO_PLATFORM', '-DLIMITED_FLOOD')
        result, report = self.diagnose('--library', str(library))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report.get('code'), -1001,
                         'A 16 MiB native stream hit RLIMIT_FSIZE instead of returning its API error')
        self.assertIn('final driver error', report['native_stderr'])
        self.assertLess(len(report['native_stderr']), 8300)

    def test_inaccessible_copy_is_reported_without_losing_other_probes(self):
        self.build_driver()
        script = self.root / 'scripts/diagnose-adreno-opencl.py'
        spec = spec_from_file_location('adreno_diagnostics', script)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        blocked = self.vendor / 'libCB.so'
        blocked.write_bytes(b'inaccessible helper')
        original = Path.is_file

        def denied(path):
            if path == blocked:
                raise PermissionError(13, 'Permission denied', str(path))
            return original(path)

        # Root-only containers cannot reproduce access checks by dropping uid.
        # Inject only this filesystem denial; the three native probes run for real.
        with patch.object(Path, 'is_file', denied):
            try:
                report = module.compare(self.env, 2)
            except PermissionError as error:
                self.fail(f'An inaccessible helper aborted the diagnostic: {error}')
        self.assertEqual(len(report['probes']), 3)
        self.assertIn('libCB.so', json.dumps(report['copy_errors']))
        self.assertIn('Permission denied', json.dumps(report['copy_errors']))

    def test_probe_reports_actual_platform_gpu_and_driver(self):
        result, report = self.probe(self.build_driver())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report['ready'])
        gpu = report['platforms'][0]['gpus'][0]
        self.assertEqual(gpu['name'], 'Adreno (TM) 750')
        self.assertEqual(gpu['driver'], 'fixture-driver')

    def test_no_platform_reports_opencl_error_without_success(self):
        result, report = self.probe(self.build_driver('-DNO_PLATFORM'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report['ready'])
        self.assertEqual(report['stage'], 'platforms')
        self.assertEqual(report['code'], -1001)

    def test_platform_without_gpu_is_not_ready(self):
        result, report = self.probe(self.build_driver('-DNO_GPU'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report['ready'])
        self.assertEqual(report['stage'], 'gpu-devices')

    def test_missing_driver_reports_dynamic_linker_error(self):
        result, report = self.probe(self.vendor / 'absent.so')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['stage'], 'load-library')
        self.assertIn('absent.so', report['error'])

    def test_install_copies_sidecar_without_overwriting_termux_loader(self):
        driver = self.build_driver()
        sidecar = self.vendor / 'libOpenCL_adreno.so'
        shutil.copy2(driver, sidecar)
        loader = self.prefix / 'lib/libOpenCL.so'
        loader.write_bytes(b'leave-package-loader-alone')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        current = self.root / 'runtime/adreno-opencl/current'
        self.assertTrue(current.is_symlink())
        self.assertTrue((current / 'verified').exists())
        self.assertEqual((current / 'lib/libOpenCL_adreno.so').read_bytes(), sidecar.read_bytes())
        self.assertEqual(loader.read_bytes(), b'leave-package-loader-alone')

    def test_failed_reprobe_keeps_previous_working_install(self):
        self.build_driver()
        installed = self.install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        current = self.root / 'runtime/adreno-opencl/current'
        previous = current.resolve()
        self.build_driver('-DNO_PLATFORM')
        result = self.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(current.resolve(), previous)
        self.assertIn('platforms', result.stdout)

    def test_native_driver_crash_does_not_activate_an_install(self):
        self.build_driver('-DCRASH')
        result = self.install()
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('probe failed', result.stderr)
        self.assertFalse((self.root / 'runtime/adreno-opencl/current').exists())


if __name__ == '__main__':
    unittest.main()
