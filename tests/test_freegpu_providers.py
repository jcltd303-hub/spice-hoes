import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import hashlib
import json
import shutil
import subprocess

from PIL import Image

from spicecore.freegpu import read_bundle, write_result
from spicecore.media.pipeline import MediaPipeline
from spicecore.media.providers.freegpu import BatchPending, FreeGPUVideoProvider, FreeGPULipSyncProvider
from spicecore.media.models import RenderState, MediaJob, QAReport


class FreeGPUProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / 'approved.png'
        Image.new('RGB', (32, 48), 'blue').save(self.image)
        self.provider = FreeGPUVideoProvider(self.root / 'queue')

    def test_missing_result_creates_one_durable_request_across_retries(self):
        for _ in range(2):
            with self.assertRaises(BatchPending):
                self.provider.image_to_video(str(self.image), 'A gentle head turn')
        jobs = list((self.root / 'queue/jobs').glob('*.zip'))
        self.assertEqual(len(jobs), 1)
        manifest = read_bundle(jobs[0])
        self.assertEqual(manifest['task'], 'video')
        self.assertEqual(manifest['options']['pipeline'], 'svd-i2v')
        self.assertTrue(manifest['approved_fictional_persona'])

    def test_matching_result_resumes_generation_after_restart(self):
        with self.assertRaises(BatchPending):
            self.provider.image_to_video(str(self.image), 'A gentle head turn')
        job = next((self.root / 'queue/jobs').glob('*.zip'))
        output = self.root / 'rendered.mp4'
        output.write_bytes(b'video-placeholder-for-transport-test')
        write_result(job, self.root / 'queue/results/result.zip', artifacts={'video.mp4': output})
        restarted = FreeGPUVideoProvider(self.root / 'queue')
        result = restarted.image_to_video(str(self.image), 'A gentle head turn')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['cost_cents'], 0)
        self.assertEqual(Path(result['video_path']).read_bytes(), output.read_bytes())

    def test_preflight_exports_all_scenes_before_voice_or_rendering(self):
        voice = Mock()
        pipeline = MediaPipeline(video_provider=self.provider, voice_provider=voice,
                                 lipsync_provider=Mock(), output_dir=str(self.root / 'render'))
        job = pipeline.create_job('zara_voss', 'candidate', str(self.image), 'Hello. Today is creative. Explore it.')
        result = pipeline.render(job)
        self.assertEqual(len(list((self.root / 'queue/jobs').glob('*.zip'))), 3)
        self.assertEqual(result.status, RenderState.RENDER_FAILED)
        self.assertIn('Waiting for attended GPU', result.error_message)
        voice.synthesize.assert_not_called()

    def test_changed_source_image_produces_new_job(self):
        with self.assertRaises(BatchPending):
            self.provider.image_to_video(str(self.image), 'A gentle head turn')
        Image.new('RGB', (32, 48), 'red').save(self.image)
        with self.assertRaises(BatchPending):
            self.provider.image_to_video(str(self.image), 'A gentle head turn')
        self.assertEqual(len(list((self.root / 'queue/jobs').glob('*.zip'))), 2)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_download_retimes_short_gpu_video_to_scene_duration(self):
        with self.assertRaises(BatchPending):
            self.provider.image_to_video(str(self.image), 'A gentle head turn', duration_seconds=5)
        bundle = next((self.root / 'queue/jobs').glob('*.zip'))
        clip = self.root / 'gpu.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x96:r=7:d=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], check=True)
        write_result(bundle, self.root / 'queue/results/video.zip', artifacts={'video.mp4': clip})
        result = self.provider.image_to_video(str(self.image), 'A gentle head turn', duration_seconds=5)
        path = self.provider.download(result['job_id'], str(self.root / 'retimed.mp4'))
        probe = subprocess.run(['ffprobe', '-v', 'error', '-of', 'json', '-show_streams', '-show_format', path],
                               check=True, capture_output=True, text=True)
        metadata = json.loads(probe.stdout)
        self.assertAlmostEqual(float(metadata['format']['duration']), 5.0, delta=.1)
        self.assertEqual(metadata['streams'][0]['r_frame_rate'], '30/1')

    def test_lipsync_retry_after_restart_reuses_exact_speech_and_base_video(self):
        voice = Mock()
        calls = []
        def speak(**kwargs):
            calls.append(kwargs['text'])
            Path(kwargs['output_path']).write_bytes(b'speech-' + str(len(calls)).encode())
            return {'provider': 'android-offline', 'cost_cents': 0}
        voice.synthesize.side_effect = speak
        video = Mock(spec=['image_to_video', 'download'])
        video.image_to_video.return_value = {'job_id': 'clip', 'provider': 'free-gpu-batch', 'cost_cents': 0}
        video.download.side_effect = lambda _id, path: Path(path).write_bytes(b'clip')
        lip = FreeGPULipSyncProvider(self.root / 'queue')
        def pipeline():
            instance = MediaPipeline(video_provider=video, voice_provider=voice, lipsync_provider=lip,
                                     output_dir=str(self.root / 'render'))
            instance.assembler = Mock()
            instance.assembler.assemble.side_effect = lambda **kw: Path(kw['output_mp4_path']).write_bytes(b'assembled')
            instance.qa_validator = Mock()
            instance.qa_validator.evaluate.return_value = QAReport(True, 1.0)
            return instance
        first = pipeline()
        job = first.create_job('zara_voss', 'candidate', str(self.image), 'Hello. A creative day. Explore it.')
        self.assertEqual(first.render(job).status, RenderState.RENDER_FAILED)
        bundle = next((self.root / 'queue/jobs').glob('*.zip'))
        original_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
        restored = MediaJob.from_dict(job.to_dict())
        second = pipeline()
        self.assertEqual(second.render(restored).status, RenderState.RENDER_FAILED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(len(list((self.root / 'queue/jobs').glob('*.zip'))), 1)
        returned = self.root / 'synced.mp4'
        returned.write_bytes(b'gpu-lipsynced')
        write_result(bundle, self.root / 'queue/results/synced.zip', artifacts={'lipsync.mp4': returned})
        third = pipeline()
        self.assertEqual(third.render(restored).status, RenderState.REVIEW_READY)
        self.assertEqual(len(calls), 1)
        final_call = third.assembler.assemble.call_args.kwargs
        self.assertTrue(final_call['caption_file_path'].endswith('captions.srt'))
        self.assertEqual(Path(final_call['scene_video_paths'][0]).read_bytes(), b'gpu-lipsynced')
