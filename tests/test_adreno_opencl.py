import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <signal.h>
typedef void * id;
int clGetPlatformIDs(unsigned n, id *out, unsigned *count) {
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
        for name in ('setup-adreno-opencl.sh', 'probe-opencl.py'):
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
