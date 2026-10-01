"""Provider adapters for OpenAI-compatible text and local-dream media."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ProviderError(str(exc)) from exc


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
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def chat(self, system: str, user: str, temperature: float = 0.4) -> str:
        data = _post_json(
            f"{self.base_url}/chat/completions",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
            self._headers(),
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected OpenAI-compatible response") from exc


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


class LocalDreamProvider:
    """Adapter for local-dream generation and local identity scoring."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("LOCAL_DREAM_URL", "http://127.0.0.1:7860")).rstrip("/")
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

        data = _post_json(
            f"{self.base_url}/generate",
            payload,
            self._headers(),
            timeout=180,
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
