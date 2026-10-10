"""Durable media rendering adapters for attended notebook batches."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from ...freegpu import export_job, import_result, read_bundle
from .video import VideoProvider
from .lipsync import LipSyncProvider


class BatchPending(RuntimeError):
    pass


class BatchBridge:
    def __init__(self, directory=None):
        self.root = Path(directory or os.getenv('SPICE_FREEGPU_DIR', 'data/freegpu')).absolute()
        self.jobs = self.root / 'jobs'
        self.results = self.root / 'results'
        for directory in (self.jobs, self.results):
            directory.mkdir(parents=True, exist_ok=True)

    def ensure(self, task, inputs, options):
        signature = {'task': task, 'inputs': dict(inputs), 'options': options}
        for key in ('image', 'audio', 'video'):
            if key in inputs:
                path = Path(inputs[key])
                if not path.is_file() or path.is_symlink():
                    raise ValueError('Free GPU inputs must be explicit local files')
                digest = hashlib.sha256()
                with path.open('rb') as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(chunk)
                signature['inputs'][key] = {'sha256': digest.hexdigest(), 'extension': path.suffix.lower()}
        job_id = task + '-' + hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        bundle = self.jobs / (job_id + '.zip')
        if not bundle.exists():
            export_job(bundle, task=task, inputs=inputs, options=options,
                       approved_fictional_persona=True, job_id=job_id)
        job = read_bundle(bundle)
        if job['job_id'] != job_id:
            raise ValueError('Saved batch job identity changed')
        for result_zip in sorted(self.results.glob('*.zip')):
            result = read_bundle(result_zip, kind='result')
            if result['job_id'] != job_id or result['status'] != 'completed':
                continue
            # Use a fresh extraction for each consumption so altered cached files
            # cannot bypass result ZIP validation on a retry or process restart.
            target = self.root / 'imported' / hashlib.sha256(result_zip.read_bytes()).hexdigest()
            if (target / job_id).exists():
                # Existing output must match the validated archive's metadata.
                for entry in result['files']:
                    artifact = target / job_id / entry['path']
                    if artifact.is_symlink() or not artifact.is_file():
                        raise ValueError('Imported batch artifact is missing or unsafe')
                    if hashlib.sha256(artifact.read_bytes()).hexdigest() != entry['sha256']:
                        raise ValueError('Imported batch artifact integrity changed')
                # import_result checks these fields before writing; repeat for reuse.
                from ...freegpu import manifest_sha256
                if result['job_manifest_sha256'] != manifest_sha256(job):
                    raise ValueError('Batch result does not match the current job')
                paths = [str(target / job_id / e['path']) for e in result['files']]
            else:
                paths = import_result(result_zip, job_bundle=bundle, output_dir=target)['artifact_paths']
            return {'job_id': job_id, 'status': 'completed', 'paths': paths, 'cost_cents': 0}
        raise BatchPending(f'Waiting for attended GPU results: upload {bundle}; copy the result ZIP to {self.results} and render again')


class FreeGPUVideoProvider(VideoProvider):
    batch_compute = True

    def __init__(self, directory=None):
        self.bridge = BatchBridge(directory)
        self.jobs = {}

    def image_to_video(self, image_uri, prompt, duration_seconds=5.0,
                      aspect_ratio='9:16', motion='subtle push-in', seed=None, **kwargs):
        if not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 8:
            raise ValueError('Batch scene duration must be 0..8 seconds')
        # SVD FP16 fits a common free T4. Prompt text describes the job;
        # SVD's motion is conditioned only on the image and numeric controls.
        result = self.bridge.ensure('video', {'image': image_uri, 'prompt': prompt}, {
            'pipeline': 'svd-i2v',
            'model': os.getenv('SPICE_FREEGPU_VIDEO_MODEL', 'stabilityai/stable-video-diffusion-img2vid-xt'),
            'frames': 25, 'seed': seed if seed is not None else int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:4], 'big'), 'fps': 7,
            'steps': int(os.getenv('SPICE_FREEGPU_VIDEO_STEPS', '25'))})
        path = next(p for p in result['paths'] if p.endswith('/video.mp4'))
        job = {**result, 'video_path': path, 'provider': 'free-gpu-batch',
               'duration_seconds': duration_seconds, 'aspect_ratio': aspect_ratio}
        self.jobs[job['job_id']] = job
        return job

    def prepare_batch(self, scenes, source_asset_uri, aspect_ratio):
        pending = []
        for scene in scenes:
            try:
                self.image_to_video(scene.source_asset_uri or source_asset_uri,
                                   f'{scene.motion}, {scene.dialogue}', scene.duration_seconds,
                                   aspect_ratio=aspect_ratio, motion=scene.motion)
            except BatchPending as error:
                pending.append(str(error))
        if pending:
            raise BatchPending('\n'.join(pending))

    def text_image_to_video(self, prompt, image_uri, **kwargs):
        return self.image_to_video(image_uri, prompt, **kwargs)

    def talking_head(self, image_uri, audio_uri, **kwargs):
        raise RuntimeError('Use the freegpu lip sync provider on an assembled base video')

    def status(self, job_id):
        return self.jobs[job_id]

    def download(self, job_id, destination_path):
        job = self.jobs[job_id]
        path = Path(destination_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:
            raise RuntimeError('Install FFmpeg and ffprobe to validate and retime GPU clips')
        probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1', job['video_path']],
                               check=True, capture_output=True, text=True, timeout=15)
        actual = float(probe.stdout.strip())
        if not math.isfinite(actual) or not 0 < actual <= 60:
            raise ValueError('GPU clip duration is invalid')
        factor = job['duration_seconds'] / actual
        subprocess.run([ffmpeg, '-v', 'error', '-xerror', '-y', '-protocol_whitelist', 'file,pipe',
                        '-i', job['video_path'], '-an', '-vf', f'setpts={factor:.10f}*PTS,fps=30',
                        '-t', str(job['duration_seconds']), '-c:v', 'libx264', '-preset', 'fast',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)],
                       check=True, capture_output=True, timeout=120)
        return str(path)


class FreeGPULipSyncProvider(LipSyncProvider):
    batch_compute = True
    def __init__(self, directory=None):
        self.bridge = BatchBridge(directory)
        self.jobs = {}

    def sync(self, video_uri, audio_uri, output_path=None, **kwargs):
        result = self.bridge.ensure('lipsync', {'video': video_uri, 'audio': audio_uri}, {})
        path = next(p for p in result['paths'] if p.endswith('/lipsync.mp4'))
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output_path)
        result.update(provider='free-gpu-batch', synced_video_path=str(output_path or path))
        self.jobs[result['job_id']] = result
        return result

    def status(self, job_id):
        return self.jobs[job_id]
