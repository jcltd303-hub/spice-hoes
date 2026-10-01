import os
import shutil
import tempfile
import unittest

from spicecore.media.qa import VideoQA


class TestVideoQA(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.qa = VideoQA(
            target_width=1080,
            target_height=1920,
            min_duration_seconds=3.0,
            max_duration_seconds=60.0,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_qa_passes_for_valid_mock_media(self):
        # Create a valid simulated video file
        sample_path = os.path.join(self.temp_dir, "good_video.mp4")
        with open(sample_path, "wb") as f:
            f.write(b"\x00\x00\x00\x1cftypisom" + (b"\x00" * 2048))

        simulated_meta = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                    "r_frame_rate": "30/1",
                    "duration": "15.0",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "duration": "15.0",
                },
            ],
            "format": {"duration": "15.0", "size": "2068"},
        }

        report = self.qa.evaluate(sample_path, simulated_meta=simulated_meta)
        self.assertTrue(report.passed)
        self.assertGreaterEqual(report.score, 0.85)
        self.assertTrue(report.checks["file_integrity"])
        self.assertTrue(report.checks["aspect_ratio"])
        self.assertTrue(report.checks["resolution"])
        self.assertTrue(report.checks["audio_present"])

    def test_qa_fails_for_missing_or_empty_file(self):
        empty_path = os.path.join(self.temp_dir, "empty.mp4")
        with open(empty_path, "wb") as f:
            pass

        report = self.qa.evaluate(empty_path)
        self.assertFalse(report.passed)
        self.assertEqual(report.score, 0.0)

    def test_qa_fails_for_wrong_aspect_ratio_or_no_audio(self):
        bad_video_path = os.path.join(self.temp_dir, "landscape_no_audio.mp4")
        with open(bad_video_path, "wb") as f:
            f.write(b"\x00\x00\x00\x1cftypisom" + (b"\x00" * 1024))

        simulated_meta = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,  # 16:9 Landscape instead of 9:16 vertical
                    "r_frame_rate": "30/1",
                    "duration": "10.0",
                }
                # No audio stream
            ],
            "format": {"duration": "10.0"},
        }

        report = self.qa.evaluate(bad_video_path, simulated_meta=simulated_meta)
        self.assertFalse(report.passed)
        self.assertFalse(report.checks["aspect_ratio"])
        self.assertFalse(report.checks["audio_present"])


if __name__ == "__main__":
    unittest.main()
