import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class S24LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copy2(ROOT / 'scripts/start-local-llm.sh', self.root / 'scripts')
        self.model = self.root / 'phone.gguf'
        self.model.write_bytes(b'GGUF')
        self.capture = self.root / 'launch.json'
        self.probes = self.root / 'probes'
        self.bin = self.root / 'llama-server'
        self.bin.write_text(f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
if sys.argv[1:] == ['--list-devices']:
    Path(os.environ['TEST_PROBES']).write_text('probed')
    print(os.environ['TEST_DEVICES'])
    raise SystemExit(int(os.environ.get('TEST_PROBE_EXIT', '0')))
Path(os.environ['TEST_CAPTURE']).write_text(json.dumps({{
    'args': sys.argv[1:], 'library_path': os.environ.get('LD_LIBRARY_PATH', '')
}}))
''')
        self.bin.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(('SPICE_LLM_', 'LLAMA_ARG_'))}
        self.env.update(SPICE_LLM_MODEL=str(self.model), SPICE_LLM_BIN=str(self.bin),
                        TEST_CAPTURE=str(self.capture), TEST_PROBES=str(self.probes),
                        TEST_DEVICES='Available devices:\n  Vulkan0: Adreno 750 (15180 MiB)')

    def launch(self, **overrides):
        return subprocess.run(['bash', 'scripts/start-local-llm.sh'], cwd=self.root,
                              env={**self.env, **overrides}, text=True,
                              capture_output=True, timeout=10)

    def args(self):
        return json.loads(self.capture.read_text())['args']

    def assert_cpu(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.args()
        self.assertEqual(args[args.index('--device') + 1], 'none')
        self.assertEqual(args[args.index('--n-gpu-layers') + 1], '0')
        self.assertIn('--no-kv-offload', args)
        self.assertIn('--no-op-offload', args)
        self.assertFalse(self.probes.exists(), 'CPU startup must skip device probing')

    def test_zero_layers_runs_without_gpu_probe(self):
        self.assert_cpu(self.launch(SPICE_LLM_GPU_LAYERS='0', TEST_PROBE_EXIT='134'))

    def test_device_none_disables_all_offload(self):
        self.assert_cpu(self.launch(SPICE_LLM_DEVICE='none'))

    def test_cpu_backend_export_overrides_saved_gpu_configuration(self):
        (self.root / '.env.s24').write_text('SPICE_LLM_BACKEND=vulkan\nSPICE_LLM_DEVICE=Vulkan0\n')
        self.assert_cpu(self.launch(SPICE_LLM_BACKEND='cpu'))

    def test_opencl_backend_selects_opencl_with_vulkan_also_visible(self):
        result = self.launch(SPICE_LLM_BACKEND='opencl', TEST_DEVICES=(
            'Available devices:\n  Vulkan0: Adreno 750\n  GPUOpenCL: Adreno 750'))
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.args()
        self.assertEqual(args[args.index('--device') + 1], 'GPUOpenCL')
        self.assertEqual(args[args.index('--n-gpu-layers') + 1], '99')

    def test_auto_prefers_opencl_over_vulkan_and_hexagon(self):
        result = self.launch(TEST_DEVICES=(
            'Available devices:\n  HTP0: Hexagon\n  Vulkan0: Adreno 750\n  GPUOpenCL: Adreno 750'))
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.args()
        self.assertEqual(args[args.index('--device') + 1], 'GPUOpenCL')

    def test_missing_opencl_does_not_start_another_backend(self):
        result = self.launch(SPICE_LLM_BACKEND='opencl')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('OpenCL', result.stderr)
        self.assertFalse(self.capture.exists())

    def test_opencl_backend_rejects_a_saved_vulkan_device(self):
        (self.root / '.env.s24').write_text('SPICE_LLM_DEVICE=Vulkan0\n')
        result = self.launch(SPICE_LLM_BACKEND='opencl', TEST_DEVICES=(
            'Available devices:\n  Vulkan0: Adreno 750\n  GPUOpenCL: Adreno 750'))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('SPICE_LLM_DEVICE', result.stderr)
        self.assertFalse(self.capture.exists())

    def test_default_native_binary_gets_its_own_libraries(self):
        native_bin = self.root / 'runtime/llama-snapdragon/bin/llama-server'
        native_bin.parent.mkdir(parents=True)
        shutil.copy2(self.bin, native_bin)
        native_lib = native_bin.parent.parent / 'lib'
        native_lib.mkdir()
        result = self.launch(SPICE_LLM_BIN='', SPICE_LLM_GPU_LAYERS='0', LD_LIBRARY_PATH='/termux/lib')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text())['library_path'],
                         f'{native_lib}:/termux/lib:/vendor/lib64:/system/lib64')

    def test_explicit_device_overrides_auto_selection(self):
        result = self.launch(SPICE_LLM_DEVICE='Vulkan0', TEST_DEVICES=(
            'Available devices:\n  Vulkan0: Adreno 750\n  GPUOpenCL: Adreno 750'))
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.args()
        self.assertEqual(args[args.index('--device') + 1], 'Vulkan0')

    def test_probe_failure_reports_cpu_recovery(self):
        result = self.launch(TEST_PROBE_EXIT='134')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('SPICE_LLM_BACKEND=cpu', result.stderr)
        self.assertFalse(self.capture.exists())

    def test_system_binary_does_not_load_snapdragon_artifact_libraries(self):
        native_lib = self.root / 'runtime/llama-snapdragon/lib'
        native_lib.mkdir(parents=True)
        result = self.launch(SPICE_LLM_GPU_LAYERS='0', LD_LIBRARY_PATH='/termux/lib')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text())['library_path'], '/termux/lib')

    def install_opencl_profile(self):
        profile = self.root / 'runtime/adreno-opencl/current'
        (profile / 'lib').mkdir(parents=True)
        (profile / 'verified').touch()
        source = self.root / 'vendor-opencl.so'
        source.write_bytes(b'phone-vendor-driver')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        (profile / 'SOURCE_SHA256SUMS').write_text(f'{digest}  {source}\n')
        return profile, source

    def test_opencl_uses_verified_isolated_vendor_libraries(self):
        profile, source = self.install_opencl_profile()
        result = self.launch(SPICE_LLM_BACKEND='opencl', PREFIX='/termux',
                             TEST_DEVICES='Available devices:\n  GPUOpenCL: Adreno 750',
                             LD_LIBRARY_PATH='/termux/lib')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(self.capture.read_text())['library_path'].startswith(f'{profile}/lib:'))

    def test_stale_vendor_profile_stops_before_probing_gpu(self):
        profile, source = self.install_opencl_profile()
        source.write_bytes(b'new-ROM-driver')
        result = self.launch(SPICE_LLM_BACKEND='opencl')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('setup-adreno-opencl.sh', result.stderr)
        self.assertFalse(self.probes.exists())
        self.assertFalse(self.capture.exists())

    def test_cpu_bypasses_a_stale_vendor_profile(self):
        profile, source = self.install_opencl_profile()
        source.write_bytes(b'new-ROM-driver')
        result = self.launch(SPICE_LLM_BACKEND='cpu', LD_LIBRARY_PATH='/termux/lib')
        self.assert_cpu(result)
        self.assertEqual(json.loads(self.capture.read_text())['library_path'], '/termux/lib')

    def test_platform_failure_points_to_adreno_setup(self):
        result = self.launch(SPICE_LLM_BACKEND='opencl', TEST_DEVICES=(
            'ggml_opencl: platform IDs not available.\nAvailable devices:\n  Vulkan0: Adreno 750'))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('setup-adreno-opencl.sh', result.stderr)

    def test_explicit_vulkan_does_not_activate_opencl_profile(self):
        profile, source = self.install_opencl_profile()
        result = self.launch(SPICE_LLM_BACKEND='vulkan', LD_LIBRARY_PATH='/termux/lib')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text())['library_path'], '/termux/lib')


if __name__ == '__main__':
    unittest.main()
