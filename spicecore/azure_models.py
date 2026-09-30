"""One Azure completion per call; run_moa owns retries and budget reservations."""
import asyncio
import datetime
from decimal import Decimal, ROUND_CEILING
import json
import inspect
import math
import re
from urllib.parse import urlsplit, quote


def _endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or
            not parsed.hostname.endswith('.openai.azure.com') or
            parsed.username or parsed.password or parsed.port not in (None, 443) or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Only approved Azure OpenAI HTTPS origins supported')
    return value.rstrip('/')


def _rate(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError('Verified bounded rates required')
    rate = Decimal(str(value))
    if not rate.is_finite() or rate <= 0:
        raise ValueError('Positive bounded rates required')
    return rate


class AzureModelClient:
    def __init__(self, config: dict, *, credential=None, sender=None, ledger=None):
        self.config, self.credential, self.sender, self.ledger = config, credential, sender, ledger
        self.endpoint = _endpoint(config['endpoint'])
        if self.endpoint not in [_endpoint(x) for x in config['approved_endpoints']]:
            raise ValueError('Endpoint not explicitly approved')

    def _validate(self, role, messages, limits):
        c = self.config
        if c.get('dry_run', True) is not False:
            raise ValueError('Live inference disabled in dry-run')
        if _endpoint(c['endpoint']) != self.endpoint or self.endpoint not in [_endpoint(x) for x in c['approved_endpoints']]:
            raise ValueError('Endpoint approval changed')
        credit = c['credit']
        expiry = datetime.datetime.fromisoformat(credit['expires_at'])
        if credit.get('eligible') is not True or not credit.get('evidence') or expiry.tzinfo is None or expiry <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError('Verified unexpired credit eligibility required')
        if type(c.get('daily_cap_cents')) is not int or c['daily_cap_cents'] <= 0 or not c.get('region'):
            raise ValueError('Owner daily cap and region required')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:-preview)?', c.get('api_version', '')):
            raise ValueError('Explicit API version required')
        deployment = c['deployments'][role]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', deployment['name']):
            raise ValueError('Invalid deployment')
        for key, maximum in [('max_input_tokens', 100000), ('max_output_tokens', 1024), ('max_attempts', 2), ('maximum_call_cents', c['daily_cap_cents'])]:
            if type(limits.get(key)) is not int or not 0 < limits[key] <= maximum:
                raise ValueError('Invalid '+key)
        timeout = limits.get('timeout_seconds')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError('Invalid timeout')
        if len(json.dumps(messages).encode()) > limits['max_input_tokens']:
            raise ValueError('Input bound exceeded')
        rates = (_rate(deployment.get('input_cents_per_million')), _rate(deployment.get('output_cents_per_million')))
        maximum = self._cost(limits['max_input_tokens'], limits['max_output_tokens'], rates)
        if maximum > limits['maximum_call_cents']:
            raise ValueError('Call reservation below verified rate bound')
        if self.ledger is None:
            raise ValueError('Budget reservation validator required')
        self.ledger.validate_reservation(limits.get('reservation_id'), limits.get('run_id'), limits['maximum_call_cents'], owner_cap_cents=c['daily_cap_cents'])
        return deployment, rates

    @staticmethod
    def _cost(input_tokens, output_tokens, rates):
        return int(((input_tokens*rates[0] + output_tokens*rates[1])/1000000).to_integral_value(rounding=ROUND_CEILING))

    async def complete(self, role: str, messages: list[dict], limits: dict) -> dict:
        deployment, rates = self._validate(role, messages, limits)
        # Repeat gates and atomically claim an attempt before token acquisition.
        async def dispatch():
            self._validate(role, messages, limits)
            self.ledger.validate_reservation(limits['reservation_id'], limits['run_id'], limits['maximum_call_cents'], consume=True, owner_cap_cents=self.config['daily_cap_cents'])
            url = self.endpoint+'/openai/deployments/'+quote(deployment['name'])+'/chat/completions?api-version='+self.config['api_version']
            payload = {'messages': messages, 'max_tokens': limits['max_output_tokens'], 'response_format': {'type': 'json_object'}}
            if self.sender is not None:
                response = self.sender(url, payload, limits['timeout_seconds'])
                return await response if inspect.isawaitable(response) else response
            if self.credential is None:
                raise ValueError('Explicit Azure identity credential required')
            from azure.core.pipeline.transport import AioHttpTransport, HttpRequest
            token = (await self.credential.get_token('https://cognitiveservices.azure.com/.default')).token
            request = HttpRequest('POST', url, headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
            request.set_json_body(payload)
            # Direct SDK transport has no pipeline retry or redirect policy.
            async with AioHttpTransport(use_env_settings=False) as transport:
                response = await transport.send(request, connection_timeout=limits['timeout_seconds'], read_timeout=limits['timeout_seconds'])
                await response.load_body()
                return {'status': response.status_code, 'body': json.loads(response.text())}
        result = {'deployment_id': deployment['name'], 'usage': {}, 'actual_cents': limits['maximum_call_cents'], 'output': None}
        try:
            response = await asyncio.wait_for(dispatch(), limits['timeout_seconds'])
            body = response['body']
            usage = body.get('usage', {})
            if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
                result['usage'] = usage
                cost = self._cost(usage['prompt_tokens'], usage['completion_tokens'], rates)
                result['actual_cents'] = cost
                if cost > limits['maximum_call_cents'] or usage['prompt_tokens'] > limits['max_input_tokens'] or usage['completion_tokens'] > limits['max_output_tokens']:
                    result['error'] = 'ProviderUsageOverrun'
                    self.ledger.record_overrun(limits['reservation_id'], limits['run_id'], cost)
                    return result
            if response['status'] == 200:
                result['output'] = body['choices'][0]['message']['content']
        except Exception as exc:
            result['error'] = type(exc).__name__
        return result


def managed_identity(client_id: str):
    """Explicit user-assigned identity; no DefaultAzureCredential fallback chain."""
    if not client_id:
        raise ValueError('Explicit managed identity client ID required')
    from azure.identity.aio import ManagedIdentityCredential
    return ManagedIdentityCredential(client_id=client_id)
