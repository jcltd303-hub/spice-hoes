"""Persistent SQLite repository for media jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import MediaJob, RenderState


class MediaJobRepository:
    def __init__(self, store):
        self.store = store
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.execute(
            """
            CREATE TABLE IF NOT EXISTS media_job (
                id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                job_json TEXT NOT NULL
            )
            """
        )
        self.store.db.commit()

    def save(self, job: MediaJob) -> dict:
        payload = job.to_dict()
        with self.store.db:
            self.store.db.execute(
                """
                INSERT INTO media_job(id,candidate_id,persona_id,status,updated_at,job_json)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    candidate_id=excluded.candidate_id,
                    persona_id=excluded.persona_id,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    job_json=excluded.job_json
                """,
                (
                    job.id,
                    job.candidate_id,
                    job.persona_id,
                    job.status.value if isinstance(job.status, RenderState) else str(job.status),
                    job.updated_at,
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return payload

    def create(self, **kwargs) -> dict:
        job = MediaJob(**kwargs)
        self.save(job)
        self.store.record_event(
            "media_job_created",
            {
                "media_job_id": job.id,
                "candidate_id": job.candidate_id,
                "persona_id": job.persona_id,
                "status": job.status.value,
            },
        )
        return job.to_dict()

    def get(self, job_id: str) -> MediaJob:
        row = self.store.db.execute(
            "SELECT job_json FROM media_job WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown media job: {job_id}")
        return MediaJob.from_dict(json.loads(row["job_json"]))

    def list(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self.store.db.execute(
                "SELECT job_json FROM media_job WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.store.db.execute(
                "SELECT job_json FROM media_job ORDER BY updated_at DESC"
            ).fetchall()
        return [json.loads(row["job_json"]) for row in rows]

    def review(self, job_id: str, decision: str, reviewer: str, note: str = "") -> dict:
        job = self.get(job_id)
        if job.status not in (RenderState.REVIEW_READY, RenderState.QA_PASSED):
            raise ValueError(f"Cannot review media job in status {job.status.value}")
        decision = decision.strip().lower()
        if decision not in ("approved", "rejected", "revise"):
            raise ValueError("Invalid media review decision")
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("Reviewer identity is required")
        job.reviewer = reviewer
        job.review_note = note.strip()
        job.reviewed_at = datetime.now(timezone.utc).isoformat()
        if decision == "approved":
            job.update_status(RenderState.APPROVED)
        elif decision == "rejected":
            job.update_status(RenderState.REJECTED)
        else:
            job.update_status(RenderState.REVISE)
        self.save(job)
        self.store.record_event(
            "media_asset_reviewed",
            {
                "media_job_id": job.id,
                "candidate_id": job.candidate_id,
                "persona_id": job.persona_id,
                "decision": decision,
                "reviewer": reviewer,
                "note": job.review_note,
            },
        )
        return job.to_dict()
