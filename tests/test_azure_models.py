import asyncio
import unittest
import tempfile
from spicecore.budget import BudgetLedger
from spicecore.azure_models import AzureModelClient


def configuration():
    return {'dry_run': False, 'endpoint': 'https://example.openai.azure.com',
            'approved_endpoints': ['https://example.openai.azure.com'],
            'api_version': '2024-10-21', 'region': 'eastus', 'daily_cap_cents': 100,
            'credit': {'eligible': True, 'evidence': 'owner-verified-subscription', 'expires_at': '2099-01-01T00:00:00+00:00'},
            'deployments': {'research': {'name': 'research-model', 'input_cents_per_million': 100, 'output_cents_per_million': 200}}}

LIMITS = {'max_attempts': 2, 'timeout_seconds': 30, 'max_input_tokens': 1000,
          'max_output_tokens': 1024, 'maximum_call_cents': 2}


class AzureTests(unittest.TestCase):
    def client(self, config=None, response=None):
        self.calls = []
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        ledger = BudgetLedger(folder.name+'/budget.db', 100)
        self.limits = {**LIMITS, 'reservation_id': ledger.reserve('run', 20), 'run_id': 'run'}
        def send(*args):
            self.calls.append(args)
            return response or {'status': 200, 'body': {'choices': [{'message': {'content': '{}'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}}
        return AzureModelClient(config or configuration(), sender=send, ledger=ledger)

    def call(self, client, limits=None):
        return asyncio.run(client.complete('research', [{'role': 'user', 'content': 'hi'}], limits or self.limits))

    def test_credit_expired(self):
        config = configuration()
        client = self.client(config)
        config['credit']['expires_at'] = '2000-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):
            self.call(client)
        self.assertEqual(self.calls, [])

    def test_nonazure_endpoint(self):
        config = configuration()
        config['endpoint'] = 'https://attacker.example'
        config['approved_endpoints'] = [config['endpoint']]
        with self.assertRaises(ValueError):
            self.client(config)

    def test_unknown_cost(self):
        config = configuration()
        config['deployments']['research']['input_cents_per_million'] = None
        with self.assertRaises(ValueError):
            self.call(self.client(config))
        self.assertEqual(self.calls, [])

    def test_failed_call(self):
        result = self.call(self.client(response={'status': 500, 'body': {'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}}))
        self.assertIsNone(result['output'])
        self.assertEqual(result['actual_cents'], 1)
        self.assertEqual(len(self.calls), 1)

    def test_redirect_not_followed(self):
        result = self.call(self.client(response={'status': 302, 'body': {}}))
        self.assertIsNone(result['output'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['actual_cents'], 2)

    def test_bound_and_success(self):
        result = self.call(self.client())
        self.assertEqual(result['deployment_id'], 'research-model')
        self.assertEqual(result['actual_cents'], 1)
        with self.assertRaises(ValueError):
            self.call(self.client(), {**self.limits, 'maximum_call_cents': 1, 'max_input_tokens': 10000})

    def test_dry_run_default(self):
        config = configuration()
        del config['dry_run']
        with self.assertRaises(ValueError):
            self.call(self.client(config))
        self.assertEqual(self.calls, [])

    def test_direct_call_denied_without_reservation(self):
        client = self.client()
        with self.assertRaises(ValueError):
            self.call(client, LIMITS)
        self.assertEqual(self.calls, [])

    def test_settled_reservation_denied(self):
        client = self.client()
        client.ledger.settle(self.limits['reservation_id'], 0)
        with self.assertRaises(ValueError):
            self.call(client)
        self.assertEqual(self.calls, [])

    def test_cancellation_closes_async_call(self):
        client = self.client()
        closed = []
        async def send(*args):
            try:
                await asyncio.sleep(10)
            finally:
                closed.append(True)
        client.sender = send
        result = self.call(client, {**self.limits, 'timeout_seconds': .01})
        self.assertEqual(result['actual_cents'], 2)
        self.assertEqual(closed, [True])

    def test_reservation_attempts_cannot_be_reused_forever(self):
        client = self.client()
        self.limits['reservation_id'] = client.ledger.reserve('small', 2)
        self.limits['run_id'] = 'small'
        self.call(client)
        with self.assertRaises(ValueError):
            self.call(client)
        self.assertEqual(len(self.calls), 1)

    def test_real_sdk_transport_request_contract(self):
        from unittest.mock import AsyncMock, Mock, patch
        from azure.core.pipeline.transport import AioHttpTransport
        client = self.client()
        client.sender = None
        client.credential = Mock()
        client.credential.get_token = AsyncMock(return_value=Mock(token='test-token'))
        response = Mock()
        response.status = 200
        response.headers = {'Content-Type': 'application/json'}
        response.reason = 'OK'
        response.read = AsyncMock(return_value=b'{"choices":[{"message":{"content":"{}"}}],"usage":{"prompt_tokens":10,"completion_tokens":5}}')
        session = Mock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.auto_decompress = True
        session.request = AsyncMock(return_value=response)
        session.close = AsyncMock()
        transport = AioHttpTransport(session=session, use_env_settings=False)
        with patch('azure.core.pipeline.transport.AioHttpTransport', return_value=transport):
            result = self.call(client)
        self.assertEqual(result['output'], '{}', result)
        self.assertEqual(session.request.call_count, 1)
        self.assertIs(session.request.call_args.kwargs['allow_redirects'], False)
        self.assertEqual(session.request.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')
        session.close.assert_awaited_once()

    def test_failed_call_settlement_keeps_charge_releases_unused(self):
        client = self.client(response={'status': 500, 'body': {'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}})
        result = self.call(client)
        client.ledger.settle(self.limits['reservation_id'], result['actual_cents'])
        self.assertEqual(client.ledger.committed_cents(), 1)

    def test_stricter_config_cap_blocks_ledger_mismatch(self):
        client = self.client()
        client.config['daily_cap_cents'] = 10
        with self.assertRaises(ValueError):
            self.call(client)
        self.assertEqual(self.calls, [])

    def test_provider_overrun_records_full_cost_and_halts(self):
        client = self.client(response={'status': 200, 'body': {'choices': [{'message': {'content': '{}'}}], 'usage': {'prompt_tokens': 100000, 'completion_tokens': 0}}})
        result = self.call(client)
        self.assertEqual(result['actual_cents'], 10)
        self.assertIsNone(result['output'])
        with self.assertRaises(ValueError):
            self.call(client)
        self.assertEqual(len(self.calls), 1)
        client.ledger.settle(self.limits['reservation_id'], 10)
        self.assertEqual(client.ledger.committed_cents(), 10)
