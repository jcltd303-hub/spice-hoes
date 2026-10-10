"""Local phone inference selection and service diagnostics."""

from __future__ import annotations

import ipaddress
import json
import os
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .providers import OpenAICompatibleChatProvider


def loopback_url(value: str) -> str:
    """Validate a device-local HTTP API without embedded credentials."""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ''
        local = host == 'localhost' or ipaddress.ip_address(host).is_loopback
        if (parts.scheme not in ('http', 'https') or not local or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment
                or any(ord(c) < 33 for c in value)):
            raise ValueError
        _ = parts.port
    except (ValueError, TypeError):
        raise ValueError('Local compute URL must use a loopback host without credentials or query') from None
    return value.rstrip('/')


def _get_json(url: str, timeout: float = 1.5, *, headers=None) -> dict:
    request = urllib.request.Request(url, headers={'Accept': 'application/json', **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read(1024 * 1024).decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('service returned a non-object status')
    return data


class LocalChatProvider(OpenAICompatibleChatProvider):
    """A single loaded llama.cpp model, with one request in flight per phone."""

    local_compute = True
    verified_revenue_only = True
    max_concurrent_requests = 1

    def __init__(self, base_url=None, api_key=None, model=None):
        base_url = loopback_url(base_url or os.getenv('MOA_BASE_URL', 'http://127.0.0.1:8083/v1'))
        super().__init__(base_url, api_key if api_key is not None else os.getenv('MOA_API_KEY', ''),
                         model or os.getenv('MOA_MODEL', 'spice-local'))
        self._slot = threading.Lock()
        self.chat_timeout = int(os.getenv('SPICE_LOCAL_CHAT_TIMEOUT_SECONDS', '180'))
        if not 1 <= self.chat_timeout <= 600:
            raise ValueError('SPICE_LOCAL_CHAT_TIMEOUT_SECONDS must be between 1 and 600')

    @property
    def model_name(self):
        return f'local-llama:{self.model}'

    def _headers(self):
        return {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}

    def chat_detailed(self, system, user, **kwargs):
        kwargs.pop('models', None)
        kwargs.pop('reasoning_enabled', None)
        kwargs['model'] = self.model
        with self._slot:
            return super().chat_detailed(system, user, **kwargs)

    def readiness(self):
        try:
            data = _get_json(self.base_url + '/models', headers=self._headers())
            ready = bool(data.get('data'))
        except Exception:
            ready = False
        return {'ready': ready, 'provider': 'local-llama', 'model': self.model,
                'endpoint': self.base_url, 'accelerated': None,
                'reason': None if ready else 'Start scripts/start-local-llm.sh with an installed GGUF model'}


def chat_provider():
    mode = os.getenv('SPICE_TEXT_PROVIDER', 'local').strip().lower()
    if mode in ('local', 'llama', 'llama.cpp'):
        return LocalChatProvider()
    if mode == 'openai-compatible':
        if not os.getenv('MOA_BASE_URL') or not os.getenv('MOA_MODEL'):
            raise ValueError('Explicit external chat needs MOA_BASE_URL and MOA_MODEL')
        provider = OpenAICompatibleChatProvider()
        provider.verified_revenue_only = True
        return provider
    raise ValueError('SPICE_TEXT_PROVIDER must be local or openai-compatible')


def compute_status():
    """Probe local services without spawning them or promising hardware speed."""
    try:
        provider = chat_provider()
        chat = provider.readiness() if hasattr(provider, 'readiness') else {
            'ready': False, 'provider': 'openai-compatible', 'reason': 'External provider is not probed here'}
    except Exception as error:
        chat = {'ready': False, 'reason': str(error)}
    image_url = f"http://{os.getenv('SPICE_QNN_HOST', '127.0.0.1')}:{os.getenv('SPICE_QNN_PORT', '18081')}"
    image = {'ready': False, 'provider': 'qnn-local', 'accelerated': None,
             'model_type': os.getenv('SPICE_QNN_TYPE', 'sd15npu')}
    try:
        health = _get_json(loopback_url(image_url) + '/health')
        image.update(ready=health.get('status') in ('ok', 'ready') or health.get('ok') is True
                     or health.get('ready') is True,
                     accelerated=health.get('accelerated'), runtime=health)
    except Exception:
        image['reason'] = 'Install/start the existing QNN runtime and model pack'
    model_dir = os.getenv('SPICE_QNN_MODEL_DIR', '')
    image['model_installed'] = bool(model_dir and Path(model_dir).is_dir())
    voice = {'ready': False, 'provider': 'android-offline', 'accelerated': None}
    try:
        voice_url = loopback_url(os.getenv('SPICE_ANDROID_VOICE_URL', 'http://127.0.0.1:8082'))
        voice.update(_get_json(voice_url + '/voice/health'))
        if voice.get('auth_required') and not os.getenv('SPICE_ANDROID_VOICE_TOKEN'):
            voice.update(ready=False, reason='Tap Copy voice pairing command in the companion and set SPICE_ANDROID_VOICE_TOKEN')
    except Exception:
        voice['reason'] = 'Open the updated Android companion and install an offline voice'
    return {'chat': chat, 'image': image, 'voice': voice,
            'video': {'ready': False, 'provider': 'free-gpu-batch',
                      'reason': 'Export a job and run notebooks/spice_free_gpu_media.ipynb'},
            'blockers': [name for name, value in [('chat', chat), ('image', image), ('voice', voice)]
                         if not value.get('ready')],
            'hardware_note': 'Probe GPU devices with llama-server --list-devices; NPU requires compatible QNN model graphs'}
