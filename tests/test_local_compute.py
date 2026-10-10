import concurrent.futures
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from spicecore.core import Store
from spicecore.local_compute import LocalChatProvider, chat_provider, compute_status
from spicecore.moa import MixtureOfAgents


class LocalComputeTests(unittest.TestCase):
    def test_local_chat_pins_loaded_model_without_router_extensions(self):
        provider = LocalChatProvider('http://127.0.0.1:8083/v1', model='phone-model')
        with patch('spicecore.providers._post_json') as request:
            request.return_value = {'choices': [{'message': {'content': 'ok'}}]}
            result = provider.chat('s', 'u', model='remote-model', models=['remote-fallback'])
        url, body, headers = request.call_args.args[:3]
        self.assertEqual(result, 'ok')
        self.assertEqual(url, 'http://127.0.0.1:8083/v1/chat/completions')
        self.assertEqual(body['model'], 'phone-model')
        self.assertNotIn('models', body)
        self.assertNotIn('reasoning', body)
        self.assertNotIn('X-Title', headers)

    def test_local_default_needs_no_cloud_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = chat_provider()
        self.assertIsInstance(provider, LocalChatProvider)
        self.assertEqual(provider.base_url, 'http://127.0.0.1:8083/v1')
        self.assertTrue(provider.verified_revenue_only)

    def test_authenticated_local_readiness_uses_the_same_headers_as_chat(self):
        provider = LocalChatProvider(api_key='paired-key', model='phone-model')
        with patch('spicecore.local_compute._get_json', return_value={'data': [{'id': 'phone-model'}]}) as get:
            self.assertTrue(provider.readiness()['ready'])
        self.assertEqual(get.call_args.kwargs['headers'], {'Authorization': 'Bearer paired-key'})

    def test_local_adapter_rejects_remote_hosts_and_embedded_secrets(self):
        for url in ['https://cloud.example/v1', 'http://127.0.0.1.evil.test/v1',
                    'http://user:secret@localhost:8083/v1', 'http://127.0.0.1/v1?token=secret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                LocalChatProvider(url, model='local')

    def test_local_model_requests_are_serialized(self):
        provider = LocalChatProvider(model='local')
        active = peak = 0
        lock = threading.Lock()

        def respond(*args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(.01)
            with lock:
                active -= 1
            return {'choices': [{'message': {'content': 'ok'}}]}

        with patch('spicecore.providers._post_json', side_effect=respond):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                answers = list(pool.map(lambda _: provider.chat('s', 'u'), range(4)))
        self.assertEqual(answers, ['ok'] * 4)
        self.assertEqual(peak, 1)

    def test_moa_uses_phone_model_for_all_roles(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root) / 'moa.sqlite')
            self.addCleanup(store.close)
            provider = LocalChatProvider(model='phone-model')
            with patch.dict(os.environ, {'MOA_MODEL_REVENUE': 'unrelated/model'}, clear=True), \
                    patch.object(provider, 'chat_detailed') as call:
                call.return_value = {'content': json.dumps({'action': 'test', 'evidence': []}),
                                     'model': 'phone-model'}
                result = MixtureOfAgents(provider, store).deliberate('Make a measurable sales experiment')
            self.assertEqual(call.call_count, 5)
            self.assertTrue(all(c.kwargs['model'] == 'phone-model' for c in call.call_args_list))
            self.assertTrue(all(c.kwargs['models'] == [] for c in call.call_args_list))
            self.assertTrue(all(c.kwargs['max_tokens'] <= 384 for c in call.call_args_list[:4]))
            self.assertLessEqual(call.call_args_list[-1].kwargs['max_tokens'], 768)
            self.assertEqual(result['architecture'], 'moa-v3-local')

    def test_diagnostics_report_unavailable_services_without_fake_acceleration(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch('spicecore.local_compute._get_json', side_effect=OSError('unavailable')):
            status = compute_status()
        self.assertFalse(status['chat']['ready'])
        self.assertFalse(status['image']['ready'])
        self.assertFalse(status['voice']['ready'])
        self.assertIn('chat', status['blockers'])
