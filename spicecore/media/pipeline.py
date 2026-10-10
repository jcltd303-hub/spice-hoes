"""End-to-end media rendering pipeline and state machine orchestration."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from .captions import CaptionGenerator
from .ffmpeg import FFmpegAssembler
from .models import (
    CostBreakdown,
    MediaJob,
    QAReport,
    RenderJob,
    RenderState,
)
from .qa import VideoQA
from .scene_builder import SceneBuilder
from .providers.lipsync import LipSyncProvider, lipsync_provider_from_env
from .providers.video import VideoProvider, video_provider_from_env
from .providers.voice import (
    CANONICAL_VOICE_PROFILES,
    VoiceProfile,
    VoiceProvider,
    voice_provider_from_env,
)
from .providers.freegpu import BatchPending


class MediaPipeline:
    """Orchestrates scene generation, voice synthesis, lip-sync, assembly, and automated QA."""

    def __init__(
        self,
        store: Any = None,
        video_provider: Optional[VideoProvider] = None,
        voice_provider: Optional[VoiceProvider] = None,
        lipsync_provider: Optional[LipSyncProvider] = None,
        output_dir: str = "/tmp/spice_rendered_media",
    ):
        self.store = store
        self.video_provider = video_provider or video_provider_from_env()
        self.voice_provider = voice_provider or voice_provider_from_env()
        self.lipsync_provider = lipsync_provider or lipsync_provider_from_env()
        self.output_dir = output_dir
        self.scene_builder = SceneBuilder()
        self.caption_generator = CaptionGenerator()
        self.assembler = FFmpegAssembler()
        self.qa_validator = VideoQA()
        os.makedirs(self.output_dir, exist_ok=True)

    def _record_audit_event(self, kind: str, payload: Dict[str, Any], external_id: Optional[str] = None) -> None:
        if self.store and hasattr(self.store, "record_event"):
            try:
                self.store.record_event(kind, payload, external_id=external_id)
            except Exception as e:
                logging.warning("Failed to record event %s in store: %s", kind, e)

    def create_job(
        self,
        persona_id: str,
        candidate_id: str,
        source_asset_uri: str,
        script: str,
        voice_profile: Optional[Dict[str, Any]] = None,
        aspect_ratio: str = "9:16",
        soundtrack: Optional[str] = None,
        cta: Optional[str] = None,
        offer: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> MediaJob:
        """Initializes a new media job in PLANNED state."""
        profile_dict = voice_profile
        if not profile_dict and persona_id in CANONICAL_VOICE_PROFILES:
            profile_dict = CANONICAL_VOICE_PROFILES[persona_id].to_dict()

        job = MediaJob(
            persona_id=persona_id,
            candidate_id=candidate_id,
            source_asset_uri=source_asset_uri,
            script=script,
            voice_profile=profile_dict or {},
            aspect_ratio=aspect_ratio,
            soundtrack=soundtrack,
            cta=cta,
            offer=offer,
            product_id=product_id,
            status=RenderState.PLANNED,
        )

        self._record_audit_event(
            "media_job_created",
            {
                "media_job_id": job.id,
                "persona_id": job.persona_id,
                "candidate_id": job.candidate_id,
                "aspect_ratio": job.aspect_ratio,
            },
        )
        return job

    @staticmethod
    def _file_hash(path):
        digest = hashlib.sha256()
        with Path(path).open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def _prepare_inputs(self, job, plan, job_dir):
        # Freeze exact local speech/base bytes while a notebook job is pending.
        # A new process can resume without synthesizing a different utterance.
        voice_audio_path = os.path.join(job_dir, 'speech.wav')
        pre_lipsync_path = os.path.join(job_dir, 'pre_lipsync.mp4')
        srt_path = os.path.join(job_dir, 'captions.srt')
        files = [voice_audio_path, pre_lipsync_path, srt_path]
        checkpoint = Path(job_dir) / 'render-inputs.json'
        source = Path(job.source_asset_uri)
        identity = {key: getattr(job, key) for key in (
            'persona_id', 'candidate_id', 'source_asset_uri', 'script', 'voice_profile',
            'aspect_ratio', 'soundtrack', 'cta', 'offer')}
        identity['source_sha256'] = self._file_hash(source) if source.is_file() else None
        identity['providers'] = [type(self.voice_provider).__name__, type(self.video_provider).__name__]
        signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        batch = getattr(self.lipsync_provider, 'batch_compute', False) is True
        if batch and checkpoint.exists():
            saved = json.loads(checkpoint.read_text())
            if saved['signature'] == signature:
                for file in files:
                    path = Path(file)
                    if path.is_symlink() or not path.is_file() or self._file_hash(path) != saved['files'][path.name]:
                        raise ValueError('Pending render input changed; restore it or create a new media job')
                job.costs.voice_generation_cents = saved['voice_cost_cents']
                job.costs.video_generation_cents = saved['video_cost_cents']
                job.voice_provider = saved['voice_provider']
                job.video_provider = saved['video_provider']
                job.captions = saved['captions']
                return voice_audio_path, pre_lipsync_path, srt_path, saved['duration_seconds']

        # Export all missing scene requests before doing local speech work.
        if hasattr(self.video_provider, "prepare_batch"):
            self.video_provider.prepare_batch(plan.scenes, job.source_asset_uri, job.aspect_ratio)
        voice_prof = (
            VoiceProfile.from_dict(job.voice_profile)
            if job.voice_profile
            else CANONICAL_VOICE_PROFILES.get(
                job.persona_id,
                VoiceProfile(persona_id=job.persona_id, voice_profile_id="default"),
            )
        )
        voice_audio_path = os.path.join(job_dir, "speech.wav")
        voice_res = self.voice_provider.synthesize(
            text=plan.full_script,
            voice_profile=voice_prof,
            output_path=voice_audio_path,
        )
        job.costs.voice_generation_cents = int(voice_res.get("cost_cents", 0))
        job.voice_provider = str(voice_res.get("provider", job.voice_provider))
        self._record_audit_event("voice_generated", {
            "media_job_id": job.id,
            "voice_profile_id": voice_prof.voice_profile_id,
            "cost_cents": job.costs.voice_generation_cents,
        })

        # 3. Generate Scene Video Clips
        scene_clips: List[str] = []
        video_gen_cost = 0
        for idx, scene in enumerate(plan.scenes):
            clip_path = os.path.join(job_dir, f"scene_{idx}_{scene.id}.mp4")
            v_res = self.video_provider.image_to_video(
                image_uri=scene.source_asset_uri or job.source_asset_uri,
                prompt=f"{scene.motion}, {scene.dialogue}",
                duration_seconds=scene.duration_seconds,
                aspect_ratio=job.aspect_ratio,
                motion=scene.motion,
            )
            self.video_provider.download(v_res["job_id"], clip_path)
            scene_clips.append(clip_path)
            video_gen_cost += int(v_res.get("cost_cents", 0))
            job.video_provider = str(v_res.get("provider", job.video_provider))

        job.costs.video_generation_cents = video_gen_cost
        self._record_audit_event("video_generation_completed", {
            "media_job_id": job.id,
            "scene_count": len(scene_clips),
            "cost_cents": video_gen_cost,
        })

        total_duration = sum(s.duration_seconds for s in plan.scenes)
        speech_duration = voice_res.get('duration_seconds')
        if isinstance(speech_duration, (int, float)):
            if not 0 < speech_duration <= 60:
                raise ValueError('Short-form speech must contain at most 60 seconds of audio')
            total_duration = max(total_duration, speech_duration)
            # MuseTalk follows the audio clock. Pad short utterances so it keeps
            # all planned scenes instead of cutting the video at the last word.
            if speech_duration < total_duration:
                padded = Path(job_dir) / 'speech-padded.wav'
                with wave.open(voice_audio_path, 'rb') as source, wave.open(str(padded), 'wb') as target:
                    target.setparams(source.getparams())
                    while chunk := source.readframes(8192):
                        target.writeframesraw(chunk)
                    missing = max(0, round(total_duration * source.getframerate()) - source.getnframes())
                    frame_bytes = source.getnchannels() * source.getsampwidth()
                    while missing:
                        count = min(missing, 8192)
                        target.writeframesraw(b'\0' * (count * frame_bytes))
                        missing -= count
                padded.replace(voice_audio_path)
        # 4. Generate caption estimates for the exact spoken script.
        caption_items = self.caption_generator.segment_script(
            script=plan.full_script,
            total_duration_seconds=total_duration,
        )
        srt_path = os.path.join(job_dir, "captions.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(self.caption_generator.to_srt(caption_items))

        job.captions = [
            {"start": c.start_seconds, "end": c.end_seconds, "text": c.text}
            for c in caption_items
        ]

        # 5. FFmpeg Assembly
        pre_lipsync_path = os.path.join(job_dir, "pre_lipsync.mp4")
        self.assembler.assemble(
            scene_video_paths=scene_clips,
            voice_audio_path=voice_audio_path,
            output_mp4_path=pre_lipsync_path,
            caption_file_path=None,
            metadata={
                "persona_id": job.persona_id,
                "candidate_id": job.candidate_id,
                "disclosure": "Fictional AI-generated adult character",
            },
        )
        if batch:
            saved = {'signature': signature,
                     'files': {Path(file).name: self._file_hash(file) for file in files},
                     'voice_cost_cents': job.costs.voice_generation_cents,
                     'video_cost_cents': job.costs.video_generation_cents,
                     'voice_provider': job.voice_provider, 'video_provider': job.video_provider,
                     'captions': job.captions, 'duration_seconds': total_duration}
            temporary = checkpoint.with_suffix('.tmp')
            temporary.write_text(json.dumps(saved, sort_keys=True))
            temporary.replace(checkpoint)
        return voice_audio_path, pre_lipsync_path, srt_path, total_duration

    def render(self, job: MediaJob) -> MediaJob:
        """Executes full rendering pipeline with state transitions and technical QA."""
        if job.status not in (RenderState.PLANNED, RenderState.RENDER_FAILED):
            raise ValueError(f"Job {job.id} cannot be rendered from state {job.status.value}")

        job.update_status(RenderState.RENDERING)
        job.error_message = None
        self._record_audit_event("render_started", {"media_job_id": job.id})

        job_dir = os.path.join(self.output_dir, job.id)
        os.makedirs(job_dir, exist_ok=True)

        try:
            # 1. Build Scene Specs
            plan = self.scene_builder.build_standard_plan(
                persona_id=job.persona_id,
                candidate_id=job.candidate_id,
                source_asset_uri=job.source_asset_uri,
                script=job.script,
                offer=job.offer,
                cta=job.cta,
                soundtrack=job.soundtrack,
                aspect_ratio=job.aspect_ratio,
            )

            voice_audio_path, pre_lipsync_path, srt_path, total_duration = self._prepare_inputs(job, plan, job_dir)
            final_mp4_path = os.path.join(job_dir, f"{job.persona_id}_{job.candidate_id[:8]}_vertical.mp4")
            synced_path = os.path.join(job_dir, 'lipsynced.mp4')
            sync_res = self.lipsync_provider.sync(
                video_uri=pre_lipsync_path,
                audio_uri=voice_audio_path,
                output_path=synced_path,
            )
            job.lipsync_provider = str(sync_res.get("provider", job.lipsync_provider))
            job.costs.lipsync_cents = int(sync_res.get("cost_cents", 0))
            # Notebook face animation may be low resolution. Frame/caption it
            # locally only after lip sync, preserving the original voice track.
            self.assembler.assemble(
                scene_video_paths=[str(sync_res.get('synced_video_path', synced_path))],
                voice_audio_path=voice_audio_path, output_mp4_path=final_mp4_path,
                caption_file_path=srt_path,
                metadata={'persona_id': job.persona_id, 'candidate_id': job.candidate_id,
                          'disclosure': 'Fictional AI-generated adult character'},
            )
            job.output_uri = final_mp4_path
            job.duration_seconds = total_duration
            job.costs.render_cents = int(os.getenv("SPICE_RENDER_COST_CENTS", "0"))
            job.sync_costs()

            job.update_status(RenderState.RENDERED)
            self._record_audit_event("render_completed", {
                "media_job_id": job.id,
                "output_uri": job.output_uri,
                "cost_cents": job.costs.total_cents,
            })

            # 6. Technical Video QA Gate
            qa_report = self.qa_validator.evaluate(final_mp4_path)
            job.qa_report = qa_report
            if qa_report.details.get('duration'):
                job.duration_seconds = float(qa_report.details['duration'])

            self._record_audit_event("video_qa_completed", {
                "media_job_id": job.id,
                "qa_passed": qa_report.passed,
                "score": qa_report.score,
                "checks": qa_report.checks,
            })

            if not qa_report.passed:
                job.update_status(RenderState.QA_FAILED, error_message="Technical QA checks failed")
                return job

            job.update_status(RenderState.QA_PASSED)
            job.update_status(RenderState.REVIEW_READY)
            self._record_audit_event("media_review_ready", {
                "media_job_id": job.id,
                "persona_id": job.persona_id,
            })

            return job

        except BatchPending as ex:
            job.update_status(RenderState.RENDER_FAILED, error_message=str(ex))
            self._record_audit_event("media_batch_pending", {"media_job_id": job.id, "reason": str(ex)})
            return job
        except Exception as ex:
            logging.exception("Render pipeline error: %s", ex)
            job.update_status(RenderState.RENDER_FAILED, error_message=str(ex))
            self._record_audit_event("render_failed", {
                "media_job_id": job.id,
                "error": str(ex),
            })
            return job

    def review(
        self,
        job: MediaJob,
        decision: str,  # approved, rejected, revise
        reviewer: str,
        note: str = "",
    ) -> MediaJob:
        """Human review gate for rendered media. Only approved media can be scheduled."""
        decision_clean = decision.strip().lower()
        if decision_clean not in ("approved", "rejected", "revise"):
            raise ValueError(f"Invalid review decision: {decision}. Must be 'approved', 'rejected', or 'revise'.")
        if not reviewer or not reviewer.strip():
            raise ValueError("Reviewer identity is required for review desk gate.")

        # Media must be ready for review
        if job.status not in (RenderState.REVIEW_READY, RenderState.QA_PASSED):
            raise ValueError(f"Cannot review job in status {job.status.value}. Must be review_ready.")

        job.reviewer = reviewer.strip()
        job.review_note = note.strip()

        if decision_clean == "approved":
            job.update_status(RenderState.APPROVED)
        elif decision_clean == "rejected":
            job.update_status(RenderState.REJECTED)
        elif decision_clean == "revise":
            job.update_status(RenderState.REVISE)

        self._record_audit_event("asset_reviewed", {
            "media_job_id": job.id,
            "candidate_id": job.candidate_id,
            "persona_id": job.persona_id,
            "decision": decision_clean,
            "reviewer": job.reviewer,
            "note": job.review_note,
        })
        return job
