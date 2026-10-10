#!/usr/bin/env python3
"""Report loader errors and GPU enumeration without loading a model or compiling kernels."""
import argparse
import ctypes as c
import json
import os
from pathlib import Path


def save_report(path, report):
    """An atomic checkpoint survives a subsequent crash inside the native driver."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(path)


def mapped_driver_libraries(report, function=None):
    """Identify the API's mapped file without dumping unrelated process mappings."""
    address = c.cast(function, c.c_void_p).value if function is not None else None
    paths = set()
    try:
        for line in Path('/proc/self/maps').read_text().splitlines():
            fields = line.split(None, 5)
            if len(fields) != 6 or not fields[5].startswith('/'):
                continue
            path = fields[5]
            start, end = (int(value, 16) for value in fields[0].split('-'))
            if address is not None and start <= address < end:
                report['api_library'] = path
            if Path(path).name.startswith(('libOpenCL', 'libCB.so', 'libadreno',
                                           'libllvm', 'libvndksupport', 'libbinder_ndk')):
                paths.add(path)
        report['loaded_driver_libraries'] = sorted(paths)
    except (OSError, ValueError) as error:
        report['mapping_error'] = str(error)


class OpenCLError(Exception):
    def __init__(self, operation, code):
        super().__init__(f'{operation} returned OpenCL error {code}')
        self.code = code


def check(operation, code):
    if code != 0:
        raise OpenCLError(operation, code)


def probe(library, checkpoint=None):
    report = {'library': library, 'pid': os.getpid(), 'ready': False,
              'stage': 'load-library', 'platforms': []}
    ids = None

    def progress():
        mapped_driver_libraries(report, ids)
        if checkpoint:
            checkpoint(report)

    progress()
    try:
        lib = c.CDLL(library)
        ids = lib.clGetPlatformIDs
        ids.argtypes = [c.c_uint32, c.POINTER(c.c_void_p), c.POINTER(c.c_uint32)]
        ids.restype = c.c_int32
        devices = lib.clGetDeviceIDs
        devices.argtypes = [c.c_void_p, c.c_uint64, c.c_uint32,
                           c.POINTER(c.c_void_p), c.POINTER(c.c_uint32)]
        devices.restype = c.c_int32
        platform_info, device_info = lib.clGetPlatformInfo, lib.clGetDeviceInfo
        for function in (platform_info, device_info):
            function.argtypes = [c.c_void_p, c.c_uint32, c.c_size_t,
                                 c.c_void_p, c.POINTER(c.c_size_t)]
            function.restype = c.c_int32

        def info(function, identifier, key):
            size = c.c_size_t()
            check('get-info size', function(identifier, key, 0, None, c.byref(size)))
            if not 0 < size.value <= 65536:
                raise ValueError(f'Invalid OpenCL info length: {size.value}')
            buffer = c.create_string_buffer(size.value)
            check('get-info value', function(identifier, key, size.value, buffer, None))
            return buffer.value.decode('utf-8', errors='replace')

        report['stage'] = 'platforms'
        progress()
        count = c.c_uint32()
        check('clGetPlatformIDs', ids(0, None, c.byref(count)))
        if not 0 < count.value <= 64:
            raise ValueError(f'No usable platform count: {count.value}')
        platform_ids = (c.c_void_p * count.value)()
        check('clGetPlatformIDs', ids(count.value, platform_ids, None))
        report['stage'] = 'gpu-devices'
        progress()
        for platform_id in platform_ids:
            platform = {'name': info(platform_info, platform_id, 0x0902),
                        'vendor': info(platform_info, platform_id, 0x0903), 'gpus': []}
            report['platforms'].append(platform)
            count = c.c_uint32()
            code = devices(platform_id, 4, 0, None, c.byref(count))  # CL_DEVICE_TYPE_GPU
            if code == -1:  # CL_DEVICE_NOT_FOUND; another platform can still have a GPU.
                continue
            check('clGetDeviceIDs', code)
            if not 0 < count.value <= 64:
                continue
            device_ids = (c.c_void_p * count.value)()
            check('clGetDeviceIDs', devices(platform_id, 4, count.value, device_ids, None))
            for device_id in device_ids:
                platform['gpus'].append({'name': info(device_info, device_id, 0x102B),
                                         'driver': info(device_info, device_id, 0x102D)})
        report['ready'] = any(platform['gpus'] for platform in report['platforms'])
        if report['ready']:
            report['stage'] = 'gpu-enumerated'
        else:
            report['error'] = 'OpenCL platforms are present but no GPU was enumerated.'
    except (OSError, AttributeError, ValueError, OpenCLError) as error:
        report['error'] = str(error)
        if isinstance(error, OpenCLError):
            report['code'] = error.code
            if error.code == -1001:
                report['error_name'] = 'CL_PLATFORM_NOT_FOUND_KHR'
    progress()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', default='libOpenCL.so')
    parser.add_argument('--result-file', type=Path,
                        help='Write checkpoints here; leave stdout for native driver messages.')
    args = parser.parse_args()
    # Native driver crashes must not leave large core dumps on the phone.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, resource.getrlimit(resource.RLIMIT_CORE)[1]))
    except (ImportError, OSError, ValueError):
        pass
    checkpoint = (lambda report: save_report(args.result_file, report)) if args.result_file else None
    report = probe(args.library, checkpoint)
    if not args.result_file:
        print(json.dumps(report, indent=2))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
