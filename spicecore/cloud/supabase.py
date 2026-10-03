"""Server-side Supabase archive client using REST and Storage APIs."""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional


class SupabaseArchive:
    def __init__(self, url: Optional[str] = None, secret_key: Optional[str] = None,
                 bucket: Optional[str] = None):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key = secret_key or os.getenv("SUPABASE_SECRET_KEY", "")
        self.bucket = bucket or os.getenv("SUPABASE_BUCKET", "spice-private")
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

    def _request(self, method: str, path: str, body: bytes | None = None,
                 content_type: str = "application/json", extra: dict | None = None):
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": content_type,
            **(extra or {}),
        }
        req = urllib.request.Request(f"{self.url}{path}", data=body, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            ctype = response.headers.get("content-type") or ""
            return json.loads(raw.decode("utf-8")) if raw and "json" in ctype else raw

    def record_event(self, kind: str, payload: dict[str, Any],
                     external_id: str | None = None):
        body = json.dumps({"kind": kind, "payload": payload, "external_id": external_id}).encode("utf-8")
        return self._request(
            "POST", "/rest/v1/spice_events", body,
            extra={"Prefer": "return=representation"},
        )

    def upload_file(self, local_path: str, object_path: str):
        source = Path(local_path)
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        encoded = urllib.parse.quote(object_path.strip("/"), safe="/")
        return self._request(
            "POST",
            f"/storage/v1/object/{self.bucket}/{encoded}",
            source.read_bytes(),
            mime,
            {"x-upsert": "true"},
        )
