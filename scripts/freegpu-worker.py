#!/usr/bin/env python3
"""Execute ONE attended job; no HTTP server, tunnel, fallback provider or keepalive.

Heavy imports happen inside a supervised child so a GPU OOM/timeout cannot
turn an unfinished batch into a completed result. See docs/free-gpu-media.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import wave

# Also works with the notebook's two-file source upload, without installing Spice.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spicecore.freegpu import extract_job, manifest_sha256, read_bundle, write_result


class Pending(RuntimeError):
    """Installed compute/weights cannot currently execute the requested job."""


def _binary(name):
    path = shutil.which(name)
    if not path:
        raise Pending(f"Install {name} in the attended runtime, then retry this job")
    return path


def _run(command, **kwargs):
    # No bundle-controlled shell or executable. Parent kills this process group
    # at the job deadline, including any inference/ffmpeg descendants.
    subprocess.run(command, check=True, **kwargs)


def _host_available_gib():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    return None


def _gpu(args, *, video=False):
    try:
        import torch
    except ImportError as exc:
        raise Pending("PyTorch CUDA is missing; install notebook dependencies and select a free GPU runtime") from exc
    if not torch.cuda.is_available():
        raise Pending("CUDA GPU unavailable; request a free GPU runtime when capacity is available and rerun manually")
    free, total = torch.cuda.mem_get_info()
    minimum = args.min_free_gpu_gib if video else min(args.min_free_gpu_gib, 1.0)
    if free / 1024**3 < minimum:
        raise Pending(f"Insufficient free GPU memory: {free / 1024**3:.1f} GiB; need {minimum:g} GiB")
    if video:
        available = _host_available_gib()
        if available is not None and available < args.min_host_ram_gib:
            raise Pending(f"CPU offload needs at least {args.min_host_ram_gib:g} GiB available host RAM; found {available:.1f}")
        torch.cuda.set_per_process_memory_fraction(min(args.max_gpu_gib * 1024**3 / total, 0.95))
    return torch


def _probe(path, *, kind, max_seconds):
    command = [_binary("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
               "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
               "-of", "json", str(path)]
    proc = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    info = json.loads(proc.stdout)
    duration = float(info.get("format", {}).get("duration", "nan"))
    if not math.isfinite(duration) or not 0 < duration <= max_seconds:
        raise ValueError(f"{kind} must have a finite duration of at most {max_seconds} seconds")
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == kind]
    if not streams:
        raise ValueError(f"No actual {kind} stream in media")
    if kind == "video":
        for stream in streams:
            width, height = stream.get('width', 0), stream.get('height', 0)
            if not 0 < min(width, height) <= 1080 or not max(width, height) <= 1920:
                raise ValueError('Video input/output must fit landscape or portrait 1080p')
    return duration


def _validate_video(path, *, max_seconds, audio=False):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Inference produced no video")
    duration = _probe(path, kind="video", max_seconds=max_seconds)
    if audio:
        _probe(path, kind="audio", max_seconds=max_seconds)
    # Decode the output, rather than accepting a stub MP4 header as success.
    _run([_binary("ffmpeg"), "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe",
          "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], timeout=90)
    return duration


def _video(job, inputs_dir, outputs, args):
    torch = _gpu(args, video=True)
    try:
        from diffusers.utils import export_to_video, load_image
    except ImportError as exc:
        raise Pending("Install diffusers, transformers, accelerate, sentencepiece and imageio-ffmpeg") from exc
    _binary("ffmpeg")
    _binary("ffprobe")
    options = job["options"]
    image_mode = options["pipeline"] in ("svd-i2v", "cogvideox-i2v")
    call = dict(num_videos_per_prompt=1, num_frames=options["frames"],
                width=options["width"], height=options["height"], num_inference_steps=options["steps"],
                generator=torch.Generator(device="cpu").manual_seed(options["seed"]))
    if image_mode:
        from PIL import Image, ImageOps
        image = load_image(str(inputs_dir / job["inputs"]["image"]))
        if image.width * image.height > 16_000_000:
            raise ValueError("Image input exceeds 16 megapixels")
        call["image"] = ImageOps.pad(image.convert('RGB'), (options['width'], options['height']),
                                     method=Image.Resampling.LANCZOS, color=(16, 16, 16))
    if options["pipeline"] == "svd-i2v":
        from diffusers import StableVideoDiffusionPipeline
        pipeline = StableVideoDiffusionPipeline.from_pretrained(
            options["model"], revision=options["revision"], torch_dtype=torch.float16,
            variant="fp16", low_cpu_mem_usage=True, use_safetensors=True
        )
        pipeline.enable_model_cpu_offload()
        pipeline.unet.enable_forward_chunking()
        # SVD is conditioned by image/motion, NOT text. The prompt stays in
        # the manifest as a scene descriptor; don't pass it to inference.
        call.update(fps=options["fps"], motion_bucket_id=options["motion_bucket_id"],
                    noise_aug_strength=options["noise_aug_strength"], decode_chunk_size=options["decode_chunk_size"])
        image = call.pop("image")
        with torch.inference_mode():
            frames = pipeline(image, **call).frames[0]
    else:
        from diffusers import CogVideoXPipeline, CogVideoXImageToVideoPipeline
        pipeline_class = CogVideoXImageToVideoPipeline if image_mode else CogVideoXPipeline
        # CogVideoX 2B is FP16; the optional 5B I2V uses native BF16.
        if image_mode and not torch.cuda.is_bf16_supported():
            raise Pending("CogVideoX 5B I2V needs native BF16 and more host RAM; explicitly export svd-i2v for T4")
        pipeline = pipeline_class.from_pretrained(options["model"], revision=options["revision"],
                                                  torch_dtype=torch.bfloat16 if image_mode else torch.float16,
                                                  low_cpu_mem_usage=True, use_safetensors=True)
        # Never .to('cuda') before CPU offload; bound VAE decode memory too.
        pipeline.enable_sequential_cpu_offload()
        pipeline.vae.enable_slicing()
        pipeline.vae.enable_tiling()
        call.update(prompt=job["inputs"]["prompt"], guidance_scale=options["guidance_scale"])
        with torch.inference_mode():
            frames = pipeline(**call).frames[0]
    if len(frames) != options["frames"]:
        raise ValueError("Video model returned an unexpected number of frames")
    path = outputs / "video.mp4"
    export_to_video(frames, str(path), fps=options["fps"])
    _validate_video(path, max_seconds=60)
    return {path.name: path}


def _tts(job, inputs_dir, outputs, args):
    if not args.piper_model:
        raise Pending("Supply --piper-model with an installed open-weights voice.onnx and voice.onnx.json")
    model = Path(args.piper_model).resolve()
    if not model.is_file() or not Path(str(model) + ".json").is_file():
        raise Pending("Piper voice.onnx / voice.onnx.json weights are missing; install an explicitly selected voice")
    if args.piper_bin:
        command = [_binary(args.piper_bin)]
    else:
        if importlib.util.find_spec("piper") is None:
            raise Pending("Install piper-tts in this runtime")
        command = [sys.executable, "-m", "piper"]
    path = outputs / "speech.wav"
    command += ["--model", str(model), "--output_file", str(path),
                "--speaker", str(job["options"]["speaker_id"]),
                "--length_scale", str(job["options"]["length_scale"])]
    _run(command, input=job["inputs"]["text"] + "\n", text=True)
    # WAV must contain actual PCM frames; silence/tone is never substituted.
    with wave.open(str(path), "rb") as speech:
        if speech.getnframes() <= 0 or speech.getframerate() <= 0:
            raise ValueError("Piper returned an empty WAV")
        if speech.getnframes() / speech.getframerate() > 600:
            raise ValueError("Piper audio exceeds the finite 600-second limit")
        expected = speech.getnframes() * speech.getnchannels() * speech.getsampwidth()
        if len(speech.readframes(speech.getnframes())) != expected:
            raise ValueError("Piper returned truncated PCM audio")
    return {path.name: path}


def _transcribe(job, inputs_dir, outputs, args):
    _gpu(args)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise Pending("Install faster-whisper, CUDA 12 cuBLAS and cuDNN 9 in the attended runtime") from exc
    options = job["options"]
    audio = inputs_dir / job["inputs"]["audio"]
    _probe(audio, kind="audio", max_seconds=options["max_seconds"])
    # Normalize with file-only protocols before handing data to PyAV.
    normalized = outputs.parent / "transcribe.wav"
    _run([_binary("ffmpeg"), "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe",
          "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", str(normalized)], timeout=90)
    model = WhisperModel(options["model"], device="cuda", compute_type=options["compute_type"], cpu_threads=2, num_workers=1)
    segments, info = model.transcribe(str(normalized), beam_size=3, language=options["language"],
                                      vad_filter=True, condition_on_previous_text=False)
    # This iterator performs the real GPU inference; exhausting it is essential.
    rows = [{"start": segment.start, "end": segment.end, "text": segment.text} for segment in segments]
    text = "".join(row["text"] for row in rows).strip()
    path = outputs / "transcript.json"
    path.write_text(json.dumps({"text": text, "language": info.language,
                                "duration": info.duration, "segments": rows},
                               ensure_ascii=False, allow_nan=False), encoding="utf-8")
    plain = outputs / "transcript.txt"
    # Empty transcription (no speech detected) remains truthful and JSON is
    # the required artifact; don't invent text to make a nonempty TXT.
    artifacts = {path.name: path}
    if text:
        plain.write_text(text + "\n", encoding="utf-8")
        artifacts[plain.name] = plain
    return artifacts


def _lipsync(job, inputs_dir, outputs, args):
    _gpu(args)
    if not args.musetalk_dir:
        raise Pending("Supply --musetalk-dir with an installed MuseTalk 1.5 checkout and all required weights")
    root = Path(args.musetalk_dir).resolve()
    required = ["scripts/inference.py", "models/musetalkV15/unet.pth", "models/musetalkV15/musetalk.json",
                "models/sd-vae/config.json", "models/whisper/config.json"]
    if not all((root / name).is_file() for name in required):
        raise Pending("MuseTalk checkout/weights incomplete; follow its official 1.5 weight installation (including face models)")
    options = job["options"]
    video = inputs_dir / job["inputs"]["video"]
    audio = inputs_dir / job["inputs"]["audio"]
    _probe(video, kind="video", max_seconds=options["max_seconds"])
    _probe(audio, kind="audio", max_seconds=options["max_seconds"])
    # MuseTalk's upstream code constructs ffmpeg shell strings. Give it only
    # generated ASCII paths and normalized media, never original filenames.
    normalized_video = outputs.parent / "avatar.mp4"
    normalized_audio = outputs.parent / "voice.wav"
    ffmpeg = _binary("ffmpeg")
    _run([ffmpeg, "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe", "-i", str(video),
          "-an", "-vf", f"scale=720:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,fps={options['fps']}",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", str(normalized_video)], timeout=90)
    _run([ffmpeg, "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe", "-i", str(audio),
          "-vn", "-ac", "1", "-ar", "16000", str(normalized_audio)], timeout=90)
    config = outputs.parent / "musetalk.yaml"
    # JSON is a YAML subset accepted by OmegaConf; no manual quoting pitfalls.
    config.write_text(json.dumps({"task_0": {"video_path": str(normalized_video),
                                            "audio_path": str(normalized_audio), "result_name": "lipsync.mp4"}}))
    result_dir = outputs.parent / "musetalk-results"
    command = [args.musetalk_python or sys.executable, "-m", "scripts.inference",
               "--inference_config", str(config), "--result_dir", str(result_dir),
               "--unet_model_path", str(root / "models/musetalkV15/unet.pth"),
               "--unet_config", str(root / "models/musetalkV15/musetalk.json"),
               "--version", "v15", "--use_float16", "--batch_size", "1", "--fps", str(options["fps"])]
    _run(command, cwd=root)
    generated = result_dir / "v15/lipsync.mp4"
    _validate_video(generated, max_seconds=options["max_seconds"] + 1, audio=True)
    path = outputs / "lipsync.mp4"
    shutil.copyfile(generated, path)
    return {path.name: path}


def _child(args):
    work = Path(args.work_dir)
    report = work / "status.json"
    try:
        inputs_dir = work / "job"
        job = extract_job(args.bundle, inputs_dir)
        outputs = work / "outputs"
        outputs.mkdir()
        functions = {"video": _video, "tts": _tts, "transcribe": _transcribe, "lipsync": _lipsync}
        artifacts = functions[job["task"]](job, inputs_dir, outputs, args)
        status = {"status": "completed", "blocker": None,
                  "artifacts": {name: str(path) for name, path in artifacts.items()}}
    except Pending as exc:
        status = {"status": "pending", "blocker": str(exc)[:2000], "artifacts": {}}
    except Exception as exc:
        message = str(exc)
        unavailable = isinstance(exc, (ImportError, FileNotFoundError)) or any(
            word in message.lower() for word in ("out of memory", "cuda", "cudnn", "cublas", "connection", "not found", "401", "403")
        )
        status = {"status": "pending" if unavailable else "failed",
                  "blocker": f"{type(exc).__name__}: {message}"[:2000], "artifacts": {}}
    report.write_text(json.dumps(status, allow_nan=False), encoding="utf-8")
    return 0


def _kill(process):
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def _attended(args):
    job = read_bundle(args.bundle, kind="job")
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"Choose a new result ZIP: {args.output}")
    with tempfile.TemporaryDirectory(prefix="spice-freegpu-", dir="/tmp" if os.name == "posix" else None) as temporary:
        work = Path(temporary)
        snapshot = work / "job.zip"
        shutil.copyfile(args.bundle, snapshot)
        if manifest_sha256(read_bundle(snapshot, kind="job")) != manifest_sha256(job):
            raise ValueError("Job bundle changed before execution")
        command = [sys.executable, str(Path(__file__).resolve()), str(snapshot), "--child", "--work-dir", str(work)]
        for name in ("piper_model", "piper_bin", "musetalk_dir", "musetalk_python",
                     "min_free_gpu_gib", "min_host_ram_gib", "max_gpu_gib"):
            value = getattr(args, name)
            if value is not None:
                command += ["--" + name.replace("_", "-"), str(value)]
        with (work / "worker.log").open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=(os.name == "posix"))
            try:
                code = process.wait(timeout=job["options"]["timeout_seconds"])
            except subprocess.TimeoutExpired:
                _kill(process)
                code = None
            except BaseException:
                _kill(process)
                raise
        if code is None:
            result = {"status": "pending", "blocker": "Attended batch timeout; use a shorter job or retry manually when compute is available", "artifacts": {}}
        elif code != 0 or not (work / "status.json").is_file():
            result = {"status": "pending", "blocker": f"Worker exited ({code}) before producing outputs; check installed weights and available host/GPU RAM", "artifacts": {}}
        else:
            result = json.loads((work / "status.json").read_text())
        manifest = write_result(snapshot, args.output, artifacts=result["artifacts"],
                                status=result["status"], blocker=result["blocker"])
        print(json.dumps({"job_id": manifest["job_id"], "task": manifest["task"],
                          "status": manifest["status"], "cost_cents": 0,
                          "blocker": manifest["blocker"], "result_bundle": str(args.output.resolve())}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--piper-model", help="Explicit installed voice.onnx (plus adjacent .json)")
    parser.add_argument("--piper-bin", help="Optional installed Piper executable; default: python -m piper")
    parser.add_argument("--musetalk-dir", help="Optional installed MuseTalk 1.5 checkout with weights")
    parser.add_argument("--musetalk-python", help="Optional Python executable for MuseTalk's environment")
    parser.add_argument("--min-free-gpu-gib", type=float, default=4.0)
    parser.add_argument("--min-host-ram-gib", type=float, default=8.0)
    parser.add_argument("--max-gpu-gib", type=float, default=14.0, help="PyTorch video allocation budget")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--work-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    for name in ("min_free_gpu_gib", "min_host_ram_gib", "max_gpu_gib"):
        if not math.isfinite(getattr(args, name)) or not 0.5 <= getattr(args, name) <= 256:
            parser.error(f"{name} must be finite, 0.5..256 GiB")
    if args.child:
        if not args.work_dir:
            parser.error("Internal child requires a private work directory")
        return _child(args)
    if args.output is None:
        parser.error("--output is required")
    try:
        return _attended(args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"freegpu-worker: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
