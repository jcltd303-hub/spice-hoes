"""Portable, finite, attended media jobs. This module needs only the stdlib.

The worker is scripts/freegpu-worker.py. No server or paid provider is used.
SHA-256 detects corruption; bundles are not signed assertions of provenance.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
from typing import Any, Mapping
import uuid
import zipfile


VERSION = 1
MAX_ENTRIES = 32
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_COMPRESSION_RATIO = 100
TASKS = ("video", "tts", "transcribe", "lipsync")
VIDEO_MODEL = "zai-org/CogVideoX-2b"
SVD_MODEL = "stabilityai/stable-video-diffusion-img2vid-xt"
VIDEO_PIPELINES = ("cogvideox-t2v", "svd-i2v", "cogvideox-i2v")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?\Z")
_EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg", ".webp"},
    "audio": {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"},
    "video": {".mp4", ".mov", ".webm", ".mkv"},
}
_ARTIFACTS = {
    "video": {"video.mp4"}, "tts": {"speech.wav"},
    "transcribe": {"transcript.json", "transcript.txt"}, "lipsync": {"lipsync.mp4"},
}
_PRIMARY = {"video": "video.mp4", "tts": "speech.wav",
            "transcribe": "transcript.json", "lipsync": "lipsync.mp4"}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    """Bind a result to the canonical job, including every input file's hash."""
    return hashlib.sha256(_json_bytes(manifest)).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def _path(path: str) -> str:
    if not isinstance(path, str) or len(path) > 255:
        raise ValueError("Invalid bundle path")
    if any(not _PART.fullmatch(part) or part in (".", "..") for part in path.split("/")):
        raise ValueError(f"Unsafe bundle path: {path!r}")
    return path


def _local_path(path: os.PathLike | str, *, file: bool = False) -> Path:
    # Reject links in every component BEFORE resolve() can hide them.
    candidate = Path(os.path.abspath(os.fspath(path)))
    for part in (candidate, *candidate.parents):
        if part.is_symlink():
            raise ValueError(f"Local symlink is not allowed: {part}")
    if file and not candidate.is_file():
        raise ValueError(f"Explicit local file is required: {candidate}")
    return candidate


def _number(options, name, low, high, *, integer=False):
    value = options[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not low <= value <= high or not math.isfinite(value) or (integer and not isinstance(value, int)):
        raise ValueError(f"{name} must be {'an integer' if integer else 'finite'} from {low} to {high}")


def _options(task: str, options: Mapping[str, Any]) -> dict:
    if task not in TASKS or not isinstance(options, dict):
        raise ValueError("Unknown task or invalid options")
    defaults = {"timeout_seconds": 1800}
    if task == "video":
        pipeline = options.get("pipeline", "cogvideox-t2v")
        if pipeline not in VIDEO_PIPELINES:
            raise ValueError(f"video pipeline must be one of {VIDEO_PIPELINES}")
        defaults.update(pipeline=pipeline, revision="main", seed=42)
        if pipeline == "svd-i2v":
            defaults.update(model=SVD_MODEL, width=1024, height=576, frames=25, steps=25, fps=7,
                            motion_bucket_id=127, noise_aug_strength=0.02, decode_chunk_size=2)
        else:
            defaults.update(model="zai-org/CogVideoX-5b-I2V" if pipeline == "cogvideox-i2v" else VIDEO_MODEL,
                            width=720, height=480, frames=17, steps=20, fps=8, guidance_scale=6.0)
    elif task == "tts":
        defaults.update(speaker_id=0, length_scale=1.0)
    elif task == "transcribe":
        defaults.update(model="small", language=None, compute_type="int8_float16", max_seconds=300)
    else:
        defaults.update(fps=25, max_seconds=60)
    unknown = set(options) - set(defaults)
    if unknown:
        raise ValueError(f"Unknown {task} options: {sorted(unknown)}")
    defaults.update(options)
    _number(defaults, "timeout_seconds", 1, 3600, integer=True)
    if task == "video":
        if defaults["pipeline"] == "svd-i2v":
            _number(defaults, "width", 1024, 1024, integer=True)
            _number(defaults, "height", 576, 576, integer=True)
            _number(defaults, "frames", 14, 25, integer=True)
            if defaults["frames"] not in (14, 25):
                raise ValueError("SVD frames must be 14 or 25")
            _number(defaults, "motion_bucket_id", 0, 255, integer=True)
            _number(defaults, "noise_aug_strength", 0, 1)
            _number(defaults, "decode_chunk_size", 1, 2, integer=True)
        else:
            _number(defaults, "width", 720, 720, integer=True)
            _number(defaults, "height", 480, 480, integer=True)
            _number(defaults, "frames", 9, 49, integer=True)
            if defaults["frames"] % 4 != 1:
                raise ValueError("frames must be 4*k+1 (9..49)")
            _number(defaults, "guidance_scale", 1, 10)
        for name, low, high in (("steps", 1, 50), ("fps", 1, 30), ("seed", 0, 2**32 - 1)):
            _number(defaults, name, low, high, integer=True)
        if not isinstance(defaults["revision"], str) or not _PART.fullmatch(defaults["revision"]):
            raise ValueError("Invalid model revision; use a commit hash or branch name")
    elif task == "tts":
        _number(defaults, "speaker_id", 0, 1000, integer=True)
        _number(defaults, "length_scale", 0.5, 2.0)
    elif task == "transcribe":
        _number(defaults, "max_seconds", 1, 600, integer=True)
        if defaults["language"] is not None and (
            not isinstance(defaults["language"], str) or not re.fullmatch(r"[a-z]{2,3}", defaults["language"])
        ):
            raise ValueError("language must be a Whisper language code or null")
        if defaults["compute_type"] not in ("float16", "int8_float16"):
            raise ValueError("Transcription requires CUDA float16 or int8_float16")
    else:
        _number(defaults, "fps", 1, 30, integer=True)
        _number(defaults, "max_seconds", 1, 60, integer=True)
    if "model" in defaults and (not isinstance(defaults["model"], str) or not _MODEL.fullmatch(defaults["model"])):
        raise ValueError("model must be an explicit Hugging Face ID or Whisper model name")
    return defaults


def _inputs(task: str, inputs: dict, options: dict, approved: bool) -> None:
    if not isinstance(inputs, dict) or not isinstance(approved, bool):
        raise ValueError("Invalid inputs or asset approval")
    required = {"video": {"prompt"}, "tts": {"text"}, "transcribe": {"audio"}, "lipsync": {"video", "audio"}}[task]
    allowed = required | ({"image"} if task == "video" else set())
    if not required <= set(inputs) or set(inputs) - allowed:
        raise ValueError(f"{task} requires {sorted(required)}; allowed inputs: {sorted(allowed)}")
    for key in ("prompt", "text"):
        if key in inputs and (not isinstance(inputs[key], str) or not inputs[key].strip() or len(inputs[key]) > 4000):
            raise ValueError(f"{key} must contain 1..4000 characters")
    if ("image" in inputs or "video" in inputs) and not approved:
        raise ValueError("Image/video assets must be explicitly approved fictional-persona assets")
    if task == "video" and (options["pipeline"] in ("svd-i2v", "cogvideox-i2v")) != ("image" in inputs):
        raise ValueError("I2V requires an approved image; cogvideox-t2v requires only a prompt")


def _records(manifest: dict, prefix: str) -> dict:
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) >= MAX_ENTRIES:
        raise ValueError("Invalid files list or entry limit")
    result = {}
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise ValueError("Each file requires path, size and sha256")
        name = _path(entry["path"])
        if not name.startswith(prefix + "/") or name.count("/") != 1 or name.casefold() in result:
            raise ValueError("Invalid or duplicate file path")
        size = entry["size"]
        if type(size) is not int or not 1 <= size <= MAX_FILE_BYTES:
            raise ValueError("File size exceeds limit or is empty")
        if not isinstance(entry["sha256"], str) or not _HASH.fullmatch(entry["sha256"]):
            raise ValueError("Invalid file hash")
        result[name.casefold()] = entry
    if sum(item["size"] for item in files) > MAX_TOTAL_BYTES:
        raise ValueError("Total file size exceeds limit")
    return result


def _validate(manifest: dict, kind: str) -> None:
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int or manifest["version"] != VERSION:
        raise ValueError("Unsupported manifest version")
    if manifest.get("kind") != kind or kind not in ("job", "result"):
        raise ValueError("Wrong bundle kind")
    if not isinstance(manifest.get("job_id"), str) or not _ID.fullmatch(manifest["job_id"]):
        raise ValueError("Invalid job_id")
    task = manifest.get("task")
    if not isinstance(task, str) or task not in TASKS:
        raise ValueError("Unknown task")
    options = _options(task, manifest.get("options"))
    if options != manifest["options"]:
        raise ValueError("Manifest must specify all finite options")
    _inputs(task, manifest.get("inputs"), options, manifest.get("approved_fictional_persona"))
    common = {"version", "kind", "job_id", "task", "inputs", "options", "approved_fictional_persona", "files"}
    if kind == "job":
        if set(manifest) != common:
            raise ValueError("Unknown or missing job manifest fields")
        records = _records(manifest, "inputs")
        paths = []
        for role in _EXTENSIONS:
            if role not in manifest["inputs"]:
                continue
            name = _path(manifest["inputs"][role])
            extension = Path(name).suffix
            if extension not in _EXTENSIONS[role] or name != f"inputs/{role}{extension}":
                raise ValueError("Invalid media input path/extension")
            paths.append(name)
        if set(paths) != {item["path"] for item in records.values()}:
            raise ValueError("Input files do not match declared inputs")
    else:
        if set(manifest) != common | {"status", "cost_cents", "blocker", "job_manifest_sha256"}:
            raise ValueError("Unknown or missing result manifest fields")
        if type(manifest["cost_cents"]) is not int or manifest["cost_cents"] != 0:
            raise ValueError("Free worker results must have cost_cents=0")
        if not isinstance(manifest["job_manifest_sha256"], str) or not _HASH.fullmatch(manifest["job_manifest_sha256"]):
            raise ValueError("Invalid source job manifest hash")
        records = _records(manifest, "artifacts")
        names = {Path(item["path"]).name for item in records.values()}
        if not names <= _ARTIFACTS[task]:
            raise ValueError("Unexpected artifact for task")
        if manifest["status"] == "completed":
            if _PRIMARY[task] not in names or manifest["blocker"] is not None:
                raise ValueError("Completed result must contain the task artifact and no blocker")
        elif manifest["status"] in ("pending", "failed"):
            if records or not isinstance(manifest["blocker"], str) or not manifest["blocker"].strip() or len(manifest["blocker"]) > 2000:
                raise ValueError("Pending/failed result requires a blocker and no artifacts")
        else:
            raise ValueError("Invalid result status")


def _hash_stream(stream, *, limit=MAX_FILE_BYTES, output=None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ValueError("File size exceeds limit")
        digest.update(chunk)
        if output is not None:
            output.write(chunk)
    return size, digest.hexdigest()


def _zip_preflight(path):
    # ZipFile allocates a ZipInfo for each central-directory record. Bound
    # that allocation before opening it, rather than after infolist().
    with path.open("rb") as stream:
        size = path.stat().st_size
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise ValueError("Missing ZIP end directory")
    _, disk, directory_disk, on_disk, entries, directory_bytes, directory_offset, comment = struct.unpack_from(
        "<4s4H2LH", tail, offset
    )
    if offset + 22 + comment != len(tail):
        raise ValueError("Invalid ZIP end directory")
    if disk or directory_disk or on_disk != entries:
        raise ValueError("Multi-disk ZIP is unsupported")
    if not 1 <= entries <= MAX_ENTRIES or directory_bytes > 64 * 1024:
        raise ValueError("ZIP entries/directory exceed limit (ZIP64 unsupported)")
    if directory_offset + directory_bytes != size - len(tail) + offset:
        raise ValueError("Invalid ZIP directory extent")


@contextmanager
def _checked_archive(bundle, kind):
    path = _local_path(bundle, file=True)
    if path.stat().st_size > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES + 1024 * 1024:
        raise ValueError("ZIP file size exceeds limit")
    _zip_preflight(path)
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= MAX_ENTRIES:
                raise ValueError("ZIP entries exceed limit")
            seen = set()
            for info in infos:
                _path(info.orig_filename)
                mode = stat.S_IFMT(info.external_attr >> 16)
                if info.is_dir() or mode not in (0, stat.S_IFREG):
                    raise ValueError("ZIP symlinks, directories and special files are forbidden")
                if info.filename.casefold() in seen:
                    raise ValueError("Duplicate ZIP entry")
                seen.add(info.filename.casefold())
                limit = MAX_MANIFEST_BYTES if info.filename == "manifest.json" else MAX_FILE_BYTES
                if info.file_size > limit:
                    raise ValueError("ZIP entry size exceeds limit")
                if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ValueError("Unsupported ZIP encryption/compression")
                if info.file_size / max(1, info.compress_size) > MAX_COMPRESSION_RATIO:
                    raise ValueError("ZIP compression ratio exceeds limit")
            if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES:
                raise ValueError("ZIP total size exceeds limit")
            if "manifest.json" not in archive.namelist():
                raise ValueError("Missing manifest.json")
            raw = archive.read("manifest.json")
            manifest = json.loads(raw, object_pairs_hook=_object, parse_constant=_bad_constant)
            _validate(manifest, kind)
            if set(archive.namelist()) != {"manifest.json", *(item["path"] for item in manifest["files"])}:
                raise ValueError("Unlisted or missing ZIP files")
            for entry in manifest["files"]:
                with archive.open(entry["path"]) as stream:
                    size, digest = _hash_stream(stream)
                if size != entry["size"] or digest != entry["sha256"]:
                    raise ValueError(f"File size/hash mismatch: {entry['path']}")
            yield archive, manifest
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, RuntimeError, NotImplementedError) as exc:
        raise ValueError(f"Invalid ZIP bundle: {exc}") from exc


def read_bundle(bundle, *, kind="job") -> dict:
    """Read and verify the entire bundle without extracting anything."""
    with _checked_archive(bundle, kind) as (_, manifest):
        return manifest


def _write_bundle(output, manifest, files):
    output = _local_path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite bundle: {output}")
    _validate(manifest, manifest["kind"])
    raw = _json_bytes(manifest)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest size exceeds limit")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".freegpu-", suffix=".zip", dir=output.parent)
    os.close(fd)
    try:
        # Media is already compressed; stored entries also avoid self-created ratio bombs.
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in ("manifest.json", *sorted(files)):
                # Do not embed source mtimes/modes/names or current wall time.
                # Stable job identity + contents => identical ZIP bytes.
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                if name == "manifest.json":
                    archive.writestr(info, raw)
                else:
                    with files[name].open("rb") as source, archive.open(info, "w") as target:
                        _hash_stream(source, output=target)
        read_bundle(temporary, kind=manifest["kind"])
        # Atomic create, never replace an existing file (including concurrent writers).
        try:
            os.link(temporary, output)
        except OSError as exc:
            if exc.errno not in (errno.EPERM, errno.EOPNOTSUPP, errno.EXDEV, errno.ENOSYS):
                raise
            # Android shared storage can lack hardlinks. Exclusive creation
            # still prevents overwrite; remove a partial copy on I/O error.
            with output.open("xb") as target:
                try:
                    with open(temporary, "rb") as source:
                        shutil.copyfileobj(source, target)
                except BaseException:
                    output.unlink(missing_ok=True)
                    raise
    finally:
        Path(temporary).unlink(missing_ok=True)


def _file_record(name, path):
    path = _local_path(path, file=True)
    with path.open("rb") as stream:
        size, digest = _hash_stream(stream)
    return {"path": name, "size": size, "sha256": digest}, path


def export_job(output, *, task: str, inputs: Mapping[str, Any], options=None,
               approved_fictional_persona=False, job_id=None) -> dict:
    """Create one finite job ZIP from only the explicitly provided files."""
    options = _options(task, options if options is not None else {})
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs must be a mapping")
    inputs = dict(inputs)
    _inputs(task, inputs, options, approved_fictional_persona)
    manifest = {"version": VERSION, "kind": "job", "job_id": job_id if job_id is not None else uuid.uuid4().hex,
                "task": task, "inputs": inputs, "options": options,
                "approved_fictional_persona": approved_fictional_persona, "files": []}
    files = {}
    for role in _EXTENSIONS:
        if role in inputs:
            extension = Path(inputs[role]).suffix.lower()
            if extension not in _EXTENSIONS[role]:
                raise ValueError(f"Unsupported {role} extension")
            name = f"inputs/{role}{extension}"
            entry, path = _file_record(name, inputs[role])
            files[name] = path
            inputs[role] = name
            manifest["files"].append(entry)
    _write_bundle(output, manifest, files)
    return manifest


def write_result(job_bundle, output, *, artifacts=None, status="completed", blocker=None) -> dict:
    """Package actual worker outputs, or a pending/failed blocker with no outputs."""
    job = read_bundle(job_bundle, kind="job")
    manifest = {key: job[key] for key in ("version", "job_id", "task", "inputs", "options", "approved_fictional_persona")}
    manifest.update(kind="result", job_manifest_sha256=manifest_sha256(job), status=status,
                    cost_cents=0, blocker=blocker, files=[])
    files = {}
    for name, path in (artifacts or {}).items():
        _path(name)
        if name not in _ARTIFACTS[job["task"]]:
            raise ValueError("Unexpected artifact for task")
        entry, source = _file_record("artifacts/" + name, path)
        files[entry["path"]] = source
        manifest["files"].append(entry)
    _write_bundle(output, manifest, files)
    return manifest


def _extract(archive, manifest, destination):
    destination = _local_path(destination)
    if destination.exists():
        raise FileExistsError(f"Extraction destination must be new: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".freegpu-", dir=destination.parent))
    try:
        for entry in manifest["files"]:
            target = temporary / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry["path"]) as source, target.open("xb") as output:
                size, digest = _hash_stream(source, output=output)
            if size != entry["size"] or digest != entry["sha256"]:
                raise ValueError("File size/hash changed during extraction")
        # This directory belongs to us; never extract into arbitrary existing trees.
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def extract_job(bundle, destination) -> dict:
    """Worker entrypoint: validate first, then extract into a new private directory."""
    with _checked_archive(bundle, "job") as (archive, manifest):
        _extract(archive, manifest, destination)
        return manifest


def import_result(bundle, *, job_bundle, output_dir) -> dict:
    """Verify identity and integrity before returning local artifact paths."""
    job = read_bundle(job_bundle, kind="job")
    with _checked_archive(bundle, "result") as (archive, result):
        for key in ("job_id", "task", "inputs", "options", "approved_fictional_persona"):
            if result[key] != job[key]:
                raise ValueError(f"Result {key} does not match exported job")
        if result["job_manifest_sha256"] != manifest_sha256(job):
            raise ValueError("Result source job hash mismatch")
        paths = []
        if result["status"] == "completed":
            destination = _local_path(output_dir) / job["job_id"]
            _extract(archive, result, destination)
            paths = [str(destination / entry["path"]) for entry in result["files"]]
        return {"job_id": job["job_id"], "task": job["task"], "status": result["status"],
                "cost_cents": 0, "artifact_paths": paths,
                "artifacts": {Path(path).name: path for path in paths}, "blocker": result["blocker"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Export one finite attended job")
    export.add_argument("--task", choices=TASKS, required=True)
    for name in ("prompt", "text", "image", "audio", "video"):
        export.add_argument("--" + name)
    export.add_argument("--options", default="{}", help="JSON options; see docs/free-gpu-media.md")
    export.add_argument("--model", help="Video Hugging Face ID or Whisper model name")
    export.add_argument("--pipeline", choices=VIDEO_PIPELINES)
    export.add_argument("--approved-fictional-persona", action="store_true")
    export.add_argument("--job-id")
    export.add_argument("--output", type=Path, required=True)
    imported = commands.add_parser("import", help="Verify and import a returned result ZIP")
    imported.add_argument("bundle", type=Path)
    imported.add_argument("--job", type=Path, required=True, help="Original exported job ZIP")
    imported.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            options = json.loads(args.options, object_pairs_hook=_object, parse_constant=_bad_constant)
            if not isinstance(options, dict):
                raise ValueError("--options must be a JSON object")
            for name in ("model", "pipeline"):
                if getattr(args, name) is not None:
                    options[name] = getattr(args, name)
            result = export_job(args.output, task=args.task,
                                inputs={name: getattr(args, name) for name in ("prompt", "text", "image", "audio", "video")
                                        if getattr(args, name) is not None}, options=options,
                                approved_fictional_persona=args.approved_fictional_persona, job_id=args.job_id)
        else:
            result = import_result(args.bundle, job_bundle=args.job, output_dir=args.output_dir)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, f"freegpu: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
