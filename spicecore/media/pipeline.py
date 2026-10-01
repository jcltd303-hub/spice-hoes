"""End-to-end media rendering pipeline and state machine orchestration."""

from __future__ import annotations

import logging
import os
import uuid
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
from .providers.lipsync import LipSyncProvider, MockLipSyncProvider
from .providers.video import MockVideoProvider, VideoProvider
from .providers.voice import (
    CANONICAL_VOICE_PROFILES,
    MockVoiceProvider,
    VoiceProfile,
    VoiceProvider,
)


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
        self.video_provider = video_provider or MockVideoProvider()
        self.voice_provider = voice_provider or MockVoiceProvider()
        self.lipsync_provider = lipsync_provider or MockLipSyncProvider()
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

    def render(self, job: MediaJob) -> MediaJob:
        """Executes full rendering pipeline with state transitions and technical QA."""
        if job.status not in (RenderState.PLANNED, RenderState.RENDER_FAILED):
            raise ValueError(f"Job {job.id} cannot be rendered from state {job.status.value}")

        job.update_status(RenderState.RENDERING)
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

            # 2. Synthesize Voice
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
            job.costs.voice_generation_cents = int(voice_res.get("cost_cents", 5))
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
                video_gen_cost += int(v_res.get("cost_cents", 10))

            job.costs.video_generation_cents = video_gen_cost
            self._record_audit_event("video_generation_completed", {
                "media_job_id": job.id,
                "scene_count": len(scene_clips),
                "cost_cents": video_gen_cost,
            })

            # 4. Generate Captions (SRT and VTT)
            total_duration = sum(s.duration_seconds for s in plan.scenes)
            caption_items = self.caption_generator.segment_script(
                script=job.script,
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
            final_mp4_path = os.path.join(job_dir, f"{job.persona_id}_{job.candidate_id[:8]}_vertical.mp4")
            self.assembler.assemble(
                scene_video_paths=scene_clips,
                voice_audio_path=voice_audio_path,
                output_mp4_path=final_mp4_path,
                caption_file_path=srt_path,
                metadata={
                    "persona_id": job.persona_id,
                    "candidate_id": job.candidate_id,
                    "disclosure": "Fictional AI-generated adult character",
                },
            )
            job.output_uri = final_mp4_path
            job.duration_seconds = total_duration
            job.costs.render_cents = 8
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
