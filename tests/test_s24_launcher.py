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
    Path(os.environ['TEST_PROBES']).write_text(json.dumps({{
        'library_path': os.environ.get('LD_LIBRARY_PATH', '')
    }}))
    if os.environ.get('TEST_REQUIRE_SYSTEM_FIRST'):
        paths = os.environ.get('LD_LIBRARY_PATH', '').split(':')
        termux = os.environ['PREFIX'] + '/lib'
        if '/system/lib64' not in paths or paths.index('/system/lib64') > paths.index(termux):
            print('ggml_opencl: platform IDs not available.\\nAvailable devices:\\n  Vulkan0: Adreno 750')
            raise SystemExit(0)
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

    def test_opencl_system_priority_survives_probe_and_server_exec(self):
        profile, source = self.install_opencl_profile()
        result = self.launch(SPICE_LLM_BACKEND='opencl', PREFIX='/termux',
                             TEST_REQUIRE_SYSTEM_FIRST='1',
                             TEST_DEVICES='Available devices:\n  GPUOpenCL: Adreno 750',
                             LD_LIBRARY_PATH='/termux/lib:/custom/plugins')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        probe = json.loads(self.probes.read_text())['library_path']
        started = json.loads(self.capture.read_text())['library_path']
        self.assertEqual(probe, started)
        self.assertEqual(started.split(':')[:4], [str(profile / 'lib'), '/vendor/lib64',
                                               '/vendor/lib64/egl', '/system/lib64'])
        self.assertIn('/custom/plugins', started.split(':'))

    def test_native_opencl_keeps_its_backend_libraries_ahead_of_termux(self):
        self.install_opencl_profile()
        native_bin = self.root / 'runtime/llama-snapdragon/bin/llama-server'
        native_bin.parent.mkdir(parents=True)
        shutil.copy2(self.bin, native_bin)
        native_lib = native_bin.parent.parent / 'lib'
        native_lib.mkdir()
        result = self.launch(SPICE_LLM_BIN='', SPICE_LLM_BACKEND='auto', PREFIX='/termux',
                             TEST_REQUIRE_SYSTEM_FIRST='1',
                             TEST_DEVICES='Available devices:\n  GPUOpenCL: Adreno 750',
                             LD_LIBRARY_PATH='/termux/lib')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        paths = json.loads(self.capture.read_text())['library_path'].split(':')
        args = self.args()
        self.assertEqual(args[args.index('--device') + 1], 'GPUOpenCL')
        self.assertLess(paths.index('/system/lib64'), paths.index(str(native_lib)))
        self.assertLess(paths.index(str(native_lib)), paths.index('/termux/lib'))

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

    def build_native_runtime_fixture(self, binary, runtime_dir, profile):
        """Exercise a real ELF relocation, with the phone's missing ABI symbol."""
        binary.parent.mkdir(parents=True, exist_ok=True)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        runtime_source = self.root / 'runtime.c'
        runtime_source.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
long spice_vtable[] __asm__("_ZTVNSt6__ndk117bad_function_callE") = {750};
__attribute__((constructor)) static void record_runtime_load(void) {
    const char *path = getenv("TEST_RUNTIME_LOADS");
    if (!path) return;
    char exe[4096];
    ssize_t n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
    if (n < 0) return;
    exe[n] = 0;
    FILE *f = fopen(path, "a");
    if (f) { fprintf(f, "%s\n", exe); fclose(f); }
}
''')
        runtime = runtime_dir / 'libc++_shared.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wl,-soname,libc++_shared.so',
                        str(runtime_source), '-o', str(runtime)], check=True, capture_output=True)
        wrong_source = self.root / 'wrong-runtime.c'
        wrong_source.write_text('int incompatible_runtime(void) { return 0; }\n')
        subprocess.run(['cc', '-shared', '-fPIC', '-Wl,-soname,libc++_shared.so',
                        str(wrong_source), '-o', str(profile / 'lib/libc++_shared.so')],
                       check=True, capture_output=True)
        impl_source = self.root / 'llama-impl.c'
        impl_source.write_text(r'''
#define _GNU_SOURCE
#include <dlfcn.h>
extern long spice_vtable[] __asm__("_ZTVNSt6__ndk117bad_function_callE");
const char *spice_runtime_provider(void) {
    Dl_info info;
    if (spice_vtable[0] != 750 || !dladdr(spice_vtable, &info)) return "invalid";
    return info.dli_fname;
}
''')
        subprocess.run(['cc', '-shared', '-fPIC', '-Wl,-z,now',
                        '-Wl,-soname,libllama-server-impl.so', str(impl_source),
                        '-L' + str(runtime_dir), '-l:libc++_shared.so', '-ldl',
                        '-o', str(runtime_dir / 'libllama-server-impl.so')],
                       check=True, capture_output=True)
        binary_source = self.root / 'llama-server.c'
        binary_source.write_text(r'''
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern const char *spice_runtime_provider(void);
int main(int argc, char **argv) {
    int probe = argc == 2 && !strcmp(argv[1], "--list-devices");
    const char *paths = getenv("LD_LIBRARY_PATH");
    const char *preload = getenv("LD_PRELOAD");
    FILE *f = fopen(getenv(probe ? "TEST_PROBES" : "TEST_CAPTURE"), "w");
    if (!f) return 2;
    fprintf(f, "{\"runtime\":\"%s\",\"library_path\":\"%s\","
            "\"preload\":\"%s\",\"exec_hook\":%d}",
            spice_runtime_provider(), paths ? paths : "", preload ? preload : "",
            dlsym(RTLD_DEFAULT, "spice_exec_hook") != NULL);
    fclose(f);
    if (probe) puts("Available devices:\n  GPUOpenCL: Adreno 750");
    return 0;
}
''')
        subprocess.run(['cc', '-Wl,-z,now', str(binary_source), '-L' + str(runtime_dir),
                        '-Wl,-rpath,' + str(runtime_dir), '-Wl,-rpath-link,' + str(runtime_dir),
                        '-l:libllama-server-impl.so', '-ldl', '-o', str(binary)],
                       check=True, capture_output=True)
        return runtime

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('cc'),
                         'native linker fixture requires Linux and a C compiler')
    def test_package_opencl_resolves_ndk_abi_without_changing_hal_priority(self):
        profile, source = self.install_opencl_profile()
        prefix = self.root / 'termux'
        binary = prefix / 'bin/llama-server'
        runtime = self.build_native_runtime_fixture(binary, prefix / 'lib', profile)
        hook_source = self.root / 'exec-hook.c'
        hook_source.write_text('int spice_exec_hook(void) { return 1; }\n')
        hook = prefix / 'lib/libtermux-exec.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(hook_source), '-o', str(hook)],
                       check=True, capture_output=True)
        loads = self.root / 'runtime-loads'

        # Prove that the shadow runtime fails before the executable reaches main.
        broken = subprocess.run([str(binary), '--list-devices'], env={**self.env,
            'LD_LIBRARY_PATH': f'{profile}/lib:{prefix}/lib'}, text=True,
            capture_output=True, timeout=10)
        self.assertNotEqual(broken.returncode, 0)
        self.assertIn('_ZTVNSt6__ndk117bad_function_callE', broken.stderr)
        self.assertFalse(self.probes.exists())

        result = self.launch(SPICE_LLM_BIN=str(binary), SPICE_LLM_BACKEND='opencl',
                             PREFIX=str(prefix), LD_LIBRARY_PATH=str(prefix / 'lib'),
                             LD_PRELOAD=str(hook), TEST_RUNTIME_LOADS=str(loads))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        probe = json.loads(self.probes.read_text())
        server = json.loads(self.capture.read_text())
        for record in (probe, server):
            self.assertEqual(Path(record['runtime']).resolve(), runtime.resolve())
            self.assertEqual(record['exec_hook'], 1, 'retain the existing Termux exec hook')
        self.assertEqual(probe, server, 'use the same runtime for probing and inference')
        paths = server['library_path'].split(':')
        self.assertLess(paths.index('/system/lib64'), paths.index(str(prefix / 'lib')))
        self.assertEqual(loads.read_text().splitlines(), [str(binary), str(binary)],
                         'preload the C++ runtime only into llama-server')

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('cc'),
                         'native linker fixture requires Linux and a C compiler')
    def test_native_opencl_resolves_its_bundled_ndk_runtime(self):
        profile, source = self.install_opencl_profile()
        binary = self.root / 'runtime/llama-snapdragon/bin/llama-server'
        runtime = self.build_native_runtime_fixture(binary, binary.parent.parent / 'lib', profile)
        prefix = self.root / 'termux'
        (prefix / 'lib').mkdir(parents=True)
        shutil.copy2(profile / 'lib/libc++_shared.so', prefix / 'lib')
        result = self.launch(SPICE_LLM_BIN='', SPICE_LLM_BACKEND='auto',
                             PREFIX=str(prefix), LD_LIBRARY_PATH=str(prefix / 'lib'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for record in (json.loads(self.probes.read_text()), json.loads(self.capture.read_text())):
            self.assertEqual(Path(record['runtime']).resolve(), runtime.resolve())

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('cc'),
                         'native linker fixture requires Linux and a C compiler')
    def test_cpu_does_not_replace_the_callers_preload(self):
        profile, source = self.install_opencl_profile()
        binary = self.root / 'runtime/llama-snapdragon/bin/llama-server'
        runtime = self.build_native_runtime_fixture(binary, binary.parent.parent / 'lib', profile)
        hook_source = self.root / 'exec-hook.c'
        hook_source.write_text('int spice_exec_hook(void) { return 1; }\n')
        hook = self.root / 'libtermux-exec.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(hook_source), '-o', str(hook)],
                       check=True, capture_output=True)
        result = self.launch(SPICE_LLM_BIN='', SPICE_LLM_BACKEND='cpu', LD_PRELOAD=str(hook))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads(self.capture.read_text())
        self.assertEqual(record['preload'], str(hook))
        self.assertEqual(record['exec_hook'], 1)
        self.assertEqual(Path(record['runtime']).resolve(), runtime.resolve())
        self.assertFalse(self.probes.exists())


if __name__ == '__main__':
    unittest.main()
