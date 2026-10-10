"""Provider adapters for OpenAI-compatible text and local-dream media."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import subprocess
import shutil
import time


class ProviderError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90,
               retries: int = 0, backoff_seconds: float = 1.0) -> dict:
    """POST JSON with bounded retry for rate limits and transient upstream errors."""
    last_exc = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= retries:
                raise ProviderError(f"HTTP {exc.code}: {exc.reason}") from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else backoff_seconds * (2 ** attempt)
            except (TypeError, ValueError):
                delay = backoff_seconds * (2 ** attempt)
            time.sleep(max(0.0, min(delay, 30.0)))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt >= retries:
                raise ProviderError(str(exc)) from exc
            time.sleep(backoff_seconds * (2 ** attempt))
    raise ProviderError(str(last_exc) if last_exc else "request failed")


def _post_sse_complete(url: str, payload: dict, headers: dict[str, str],
                       timeout: int = 600) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            event = ""
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = json.loads(line.split(":", 1)[1].strip())
                if event == "error":
                    raise ProviderError(str(data.get("message", "generation failed")))
                if event == "complete":
                    image = data.get("image")
                    if not isinstance(image, str) or not image:
                        raise ProviderError("generation completed without image")
                    fmt = str(data.get("format", "png")).lower()
                    return {
                        "image_base64": image,
                        "mime_type": "image/jpeg" if fmt in ("jpg", "jpeg") else "image/png",
                        **{k: v for k, v in data.items() if k not in ("type", "image", "format")},
                    }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ProviderError(str(exc)) from exc
    raise ProviderError("generation stream ended without complete event")


def _validate_b64(value: str) -> None:
    raw = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    base64.b64decode(raw, validate=True)


class OpenAICompatibleChatProvider:
    """Generic OpenAI-compatible chat adapter using only stdlib HTTP."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None):
        self.base_url = (
            base_url or os.getenv("MOA_BASE_URL", "https://openrouter.ai/api/v1")
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("MOA_API_KEY", "")
        self.model = model or os.getenv("MOA_MODEL", "openrouter/free")
        if not self.base_url or not self.model:
            raise ProviderError("MoA provider requires base URL and model")

    @property
    def model_name(self) -> str:
        return f"openai-compatible:{self.model}"

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
        title = os.getenv("OPENROUTER_APP_TITLE", "spice-hoes").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        return headers

    def chat_detailed(self, system: str, user: str, temperature: float = 0.4,
                      response_format: dict | None = None, max_tokens: int | None = None,
                      model: str | None = None, models: list[str] | tuple[str, ...] | None = None,
                      reasoning_enabled: bool | None = None) -> dict:
        requested_model = model or self.model
        payload = {
            "model": requested_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if models:
            ordered = []
            for item in [requested_model, *models]:
                if item and item not in ordered:
                    ordered.append(item)
            payload["models"] = ordered
        if response_format is not None:
            payload["response_format"] = response_format
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if reasoning_enabled is not None and "openrouter.ai" in self.base_url:
            payload["reasoning"] = {"enabled": bool(reasoning_enabled)}

        data = _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            self._headers(),
            timeout=getattr(self, "chat_timeout", 90),
            retries=int(os.getenv("MOA_HTTP_RETRIES", "3")),
            backoff_seconds=float(os.getenv("MOA_HTTP_BACKOFF_SECONDS", "1.0")),
        )
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("OpenAI-compatible response contained empty content")
            return {
                "content": content,
                "model": data.get("model") or requested_model,
                "requested_model": requested_model,
                "usage": data.get("usage") if isinstance(data.get("usage"), dict) else {},
                "id": data.get("id"),
            }
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected OpenAI-compatible response") from exc

    def chat(self, system: str, user: str, temperature: float = 0.4,
             response_format: dict | None = None, max_tokens: int | None = None,
             model: str | None = None, models: list[str] | tuple[str, ...] | None = None,
             reasoning_enabled: bool | None = None) -> str:
        return self.chat_detailed(
            system,
            user,
            temperature=temperature,
            response_format=response_format,
            max_tokens=max_tokens,
            model=model,
            models=models,
            reasoning_enabled=reasoning_enabled,
        )["content"]


class OpenAICompatibleEmbeddingProvider:
    """Optional OpenAI-compatible embeddings adapter."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None):
        self.base_url = (
            base_url or os.getenv("MOA_BASE_URL", "https://openrouter.ai/api/v1")
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("MOA_API_KEY", "")
        self.model = model or os.getenv("MOA_EMBEDDING_MODEL", "")
        if not self.base_url or not self.model:
            raise ProviderError("Embedding provider requires base URL and MOA_EMBEDDING_MODEL")

    @property
    def model_name(self) -> str:
        return f"openai-compatible-embedding:{self.model}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("embedding input cannot be empty")
        data = _post_json(
            f"{self.base_url}/embeddings",
            {"model": self.model, "input": text, "encoding_format": "float"},
            self._headers(),
            timeout=90,
        )
        try:
            vector = data["data"][0]["embedding"]
            if not isinstance(vector, list) or not vector:
                raise TypeError
            return [float(x) for x in vector]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Unexpected embedding response") from exc


class GoMediaProvider:
    """Native Go media engine adapter. Expects a spicemedia-compatible JSON CLI."""

    def __init__(self, binary: str | None = None):
        self.binary = binary or os.getenv("SPICE_MEDIA_BIN", "bin/spicemedia")

    @property
    def model_name(self) -> str:
        return "go-media:native"

    def _run(self, command: str, payload: dict, timeout: int = 240) -> dict:
        binary = self.binary
        if not os.path.isabs(binary):
            local = os.path.join(os.getcwd(), binary)
            if os.path.isfile(local) and os.access(local, os.X_OK):
                binary = local
            else:
                resolved = shutil.which(binary)
                if resolved:
                    binary = resolved
        try:
            proc = subprocess.run(
                [binary, command],
                input=json.dumps(payload).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderError(f"go media provider failed: {exc}") from exc
        try:
            data = json.loads(proc.stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError("go media provider returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise ProviderError("go media provider returned non-object response")
        return data

    def generate_image(self, prompt: str, negative_prompt: str = "", seed: int | None = None,
                       width: int = 768, height: int = 1024,
                       references: list[dict] | None = None,
                       reference_strength: float = 0.85) -> dict:
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "reference_strength": reference_strength,
            "references": references or [],
        }
        if seed is not None:
            payload["seed"] = seed
        data = self._run("generate", payload, timeout=300)
        if isinstance(data.get("image_base64"), str):
            _validate_b64(data["image_base64"])
        elif isinstance(data.get("images"), list) and data["images"]:
            first = data["images"][0]
            if isinstance(first, str):
                _validate_b64(first)
            elif isinstance(first, dict) and isinstance(first.get("base64"), str):
                _validate_b64(first["base64"])
            else:
                raise ProviderError("go media returned unsupported images[] payload")
        else:
            raise ProviderError("go media returned no image payload")
        return data

    def score_identity(self, image_base64: str, image_mime_type: str,
                       references: list[dict]) -> dict:
        return self._run("identity", {
            "image_base64": image_base64,
            "image_mime_type": image_mime_type,
            "references": references,
        }, timeout=120)

    def score_quality(self, image_base64: str, image_mime_type: str,
                      channel: str = "") -> dict:
        return self._run("quality", {
            "image_base64": image_base64,
            "image_mime_type": image_mime_type,
            "channel": channel,
        }, timeout=120)


def media_provider(name: str | None = None):
    selected = (name or os.getenv("SPICE_MEDIA_PROVIDER", "local-dream")).strip().lower()
    if selected in ("local-dream", "localdream", "ld"):
        return LocalDreamProvider()
    if selected in ("go", "go-media", "native"):
        return GoMediaProvider()
    raise ProviderError(f"unknown media provider: {selected}")


class LocalDreamProvider:
    """Adapter for local-dream generation and local identity scoring."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("LOCAL_DREAM_URL", "http://127.0.0.1:8081")).rstrip("/")
        self.token = token or os.getenv("LOCAL_DREAM_TOKEN", "")

    @property
    def model_name(self) -> str:
        return "local-dream:s24"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def generate_image(self, prompt: str, negative_prompt: str = "", seed: int | None = None,
                       width: int = 768, height: int = 1024,
                       references: list[dict] | None = None,
                       reference_strength: float = 0.85) -> dict:
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
        }
        if seed is not None:
            payload["seed"] = seed
        if references:
            payload["references"] = references
            payload["reference_strength"] = reference_strength

        data = _post_sse_complete(
            f"{self.base_url}/generate",
            payload,
            self._headers(),
            timeout=600,
        )
        if isinstance(data.get("image_base64"), str):
            _validate_b64(data["image_base64"])
        elif isinstance(data.get("images"), list) and data["images"]:
            first = data["images"][0]
            if isinstance(first, str):
                _validate_b64(first)
            elif isinstance(first, dict) and isinstance(first.get("base64"), str):
                _validate_b64(first["base64"])
            else:
                raise ProviderError("local-dream returned unsupported images[] payload")
        else:
            raise ProviderError("local-dream returned no image payload")
        return data

    def score_identity(self, image_base64: str, image_mime_type: str,
                       references: list[dict]) -> dict:
        if not references:
            raise ProviderError("identity scoring requires at least one reference")
        return _post_json(
            f"{self.base_url}/identity/score",
            {
                "image_base64": image_base64,
                "image_mime_type": image_mime_type,
                "references": references,
            },
            self._headers(),
            timeout=120,
        )

    def score_quality(self, image_base64: str, image_mime_type: str,
                      channel: str = "") -> dict:
        return _post_json(
            f"{self.base_url}/quality/score",
            {
                "image_base64": image_base64,
                "image_mime_type": image_mime_type,
                "channel": channel,
            },
            self._headers(),
            timeout=120,
        )
