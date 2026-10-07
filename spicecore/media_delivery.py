"""Deliver local still images through Azure Blob Storage for social publishing.

The container must already exist; this adapter never makes it publicly writable.
Use separate container SAS credentials: ``c``/``w`` for uploads and exactly ``r``
for the URL handed to a publishing platform. Model generation happens elsewhere.

Azure REST contracts:
https://learn.microsoft.com/en-us/rest/api/storageservices/put-blob
https://learn.microsoft.com/en-us/rest/api/storageservices/create-service-sas
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


UPLOAD_ENV = "AZURE_MEDIA_UPLOAD_CONTAINER_SAS_URL"
READ_ENV = "AZURE_MEDIA_READ_CONTAINER_SAS_URL"
_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_IMAGE_PIXELS = 25_000_000
_MAX_JPEG_BYTES = 8 * 1024 * 1024
_API_VERSION = "2023-11-03"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sas_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError
        return parsed
    except (ValueError, AttributeError, OverflowError):
        raise ValueError(f"Azure media {label} SAS needs a valid UTC timestamp") from None


@dataclass(frozen=True, repr=False)
class _ContainerSAS:
    origin: str
    path: str
    query: str

    def blob_url(self, key: str) -> str:
        return f"{self.origin}{self.path}/{key}?{self.query}"


def _sas_fields(query: str, label: str) -> dict[str, str]:
    try:
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=32)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError
        return fields
    except (ValueError, TypeError):
        raise ValueError(f"Azure media {label} SAS query is invalid") from None


def _check_sas_fields(fields: dict[str, str], label: str, allowed_resources: set[str]) -> None:
    if not all(fields.get(key) for key in ("sig", "sv", "sp", "se")) or fields.get("sr") not in allowed_resources:
        raise ValueError(f"Azure media {label} SAS needs explicit resource scope, permissions and expiry")
    if any(key in fields for key in ("si", "ss", "srt")):
        raise ValueError(f"Azure media {label} SAS must have an explicit container or blob scope")
    if "spr" in fields and fields["spr"] != "https":
        raise ValueError(f"Azure media {label} SAS must permit HTTPS only")
    permissions = fields["sp"]
    if label == "read" and permissions != "r":
        raise ValueError("Azure media read SAS must have ONLY read (r) permission")
    if label == "upload" and not ({"c", "w"} & set(permissions)):
        raise ValueError("Azure media upload SAS needs create (c) or write (w) permission")
    now = _utcnow()
    if _sas_time(fields["se"], label) <= now:
        raise ValueError(f"Azure media {label} SAS has expired")
    if fields.get("st") and _sas_time(fields["st"], label) > now:
        raise ValueError(f"Azure media {label} SAS is not yet valid")


def _parse_container_sas(value: str, label: str) -> _ContainerSAS:
    try:
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError
        if any(ord(char) < 32 for char in value):
            raise ValueError
        parts = urllib.parse.urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.username is not None
            or parts.password is not None
            or parts.port is not None
            or parts.fragment
            or not re.fullmatch(r"[a-z0-9]{3,24}\.blob\.core\.windows\.net", parts.hostname or "")
            or not re.fullmatch(r"/[a-z0-9]+(?:-[a-z0-9]+)*", parts.path)
            or not 3 <= len(parts.path[1:]) <= 63
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"Azure media {label} needs an HTTPS Azure Blob container SAS URL") from None
    _check_sas_fields(_sas_fields(parts.query, label), label, {"c"})
    return _ContainerSAS(f"https://{parts.hostname}", parts.path, parts.query)


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        # A signed request must never be redirected to another host or resource.
        return None


class AzureMediaDelivery:
    """Upload real image bytes and return a verified, separately signed read URL."""

    def __init__(self, upload_container_sas_url: str, read_container_sas_url: str, timeout: float = 30):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Azure media HTTP timeout must be between 0 and 60 seconds")
        self._upload_url = upload_container_sas_url
        self._read_url = read_container_sas_url
        self.timeout = timeout
        self._validate_configuration()
        self._opener = urllib.request.build_opener(_RejectRedirects())

    @classmethod
    def from_env(cls) -> AzureMediaDelivery:
        missing = [name for name in (UPLOAD_ENV, READ_ENV) if not os.getenv(name, "").strip()]
        if missing:
            raise ValueError("Azure media delivery requires " + ", ".join(missing))
        return cls(os.environ[UPLOAD_ENV], os.environ[READ_ENV])

    def _validate_configuration(self) -> tuple[_ContainerSAS, _ContainerSAS]:
        upload = _parse_container_sas(self._upload_url, "upload")
        read = _parse_container_sas(self._read_url, "read")
        if (upload.origin, upload.path) != (read.origin, read.path):
            raise ValueError("Azure media upload and read SAS must address the same container")
        return upload, read

    def readiness(self) -> dict[str, Any]:
        """Check configuration without a network request or disclosing credentials."""
        try:
            self._validate_configuration()
        except ValueError as error:
            return {"ready": False, "provider": "azure_blob", "reason": str(error)}
        return {"ready": True, "provider": "azure_blob", "photo_upload": True}

    def _request(self, request: urllib.request.Request, operation: str, accepted: set[int]):
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = int(response.status)
                if status not in accepted:
                    raise RuntimeError
                return status, response.headers
        except urllib.error.HTTPError as error:
            status = error.code if isinstance(error.code, int) else 0
            try:
                error.close()
            except Exception:
                pass
            if status in accepted:
                return status, {}
            raise RuntimeError(f"Azure media {operation} failed (HTTP {status})") from None
        except Exception:
            # urllib exception messages and error bodies can contain the SAS URL.
            raise RuntimeError(f"Azure media {operation} request failed") from None

    @staticmethod
    def _jpeg(path: Path) -> bytes:
        try:
            if not path.is_file() or not 0 < path.stat().st_size <= _MAX_SOURCE_BYTES:
                raise ValueError
            with Image.open(path) as image:
                if image.width * image.height > _MAX_IMAGE_PIXELS or getattr(image, "is_animated", False):
                    raise ValueError
                image.load()
                image = ImageOps.exif_transpose(image)
                if "A" in image.getbands() or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    rgb = Image.new("RGB", rgba.size, "white")
                    rgb.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    rgb = image.convert("RGB")
                result = io.BytesIO()
                # Do not carry private EXIF/location metadata into the delivered file.
                rgb.save(result, format="JPEG", quality=95, subsampling=0)
                payload = result.getvalue()
            if not payload or len(payload) > _MAX_JPEG_BYTES:
                raise ValueError
            return payload
        except Exception:
            raise ValueError("Azure media delivery requires a readable still image within photo size limits") from None

    def prepare(self, candidate: dict[str, Any]) -> str:
        upload, read = self._validate_configuration()
        source = candidate.get("media_uri") or candidate.get("asset_uri")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Media candidate requires asset_uri or explicit media_uri")
        try:
            parts = urllib.parse.urlsplit(source)
        except ValueError:
            raise ValueError("Media candidate source URI is invalid") from None
        if parts.scheme:
            if (
                parts.scheme != "https"
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
                or parts.fragment
                or any(ord(char) < 32 for char in source)
            ):
                raise ValueError("Existing remote media URI must use HTTPS without embedded credentials")
            if (parts.hostname or "").endswith(".blob.core.windows.net") and parts.query:
                fields = _sas_fields(parts.query, "read")
                if {"sig", "sp", "sv", "sr", "si"} & fields.keys():
                    _check_sas_fields(fields, "read", {"c", "b"})
            # An explicitly supplied, already hosted public URI is a caller choice.
            return source

        payload = self._jpeg(Path(source))
        key = "media/" + hashlib.sha256(payload).hexdigest() + ".jpg"
        md5 = base64.b64encode(hashlib.md5(payload, usedforsecurity=False).digest()).decode("ascii")
        common_headers = {
            "x-ms-version": _API_VERSION,
            "x-ms-date": format_datetime(_utcnow(), usegmt=True),
        }
        request = urllib.request.Request(
            upload.blob_url(key),
            data=payload,
            headers={
                **common_headers,
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(payload)),
                "Content-MD5": md5,
                "x-ms-blob-type": "BlockBlob",
                "If-None-Match": "*",
            },
            method="PUT",
        )
        # Existing content-addressed objects can be reused only after read verification.
        self._request(request, "upload", {201, 409, 412})
        url = read.blob_url(key)
        _, headers = self._request(
            urllib.request.Request(url, headers=common_headers, method="HEAD"),
            "read verification",
            {200},
        )
        if (
            headers.get("Content-Type", "").split(";")[0].strip().lower() != "image/jpeg"
            or headers.get("Content-Length") != str(len(payload))
            or headers.get("Content-MD5") != md5
        ):
            raise RuntimeError("Azure media read verification did not match the uploaded JPEG")
        self._validate_configuration()
        return url


MediaDelivery = AzureMediaDelivery
