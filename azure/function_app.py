"""Azure Functions entrypoint. Package this file at the deployment ZIP root.

Easy Auth is mandatory and validates Entra issuer/audience before forwarding.
Never expose this handler behind an ingress that permits spoofed identity headers.
"""
import base64
import json
import os
from functools import lru_cache
import azure.functions as func
from spicecore.azure_backend import AzureBudgetLedger, AzureJobStore, TableState, preflight
from spicecore.cloud_storage import AssetStore
from spicecore.control_plane import CloudJobAPI

app=func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@lru_cache(maxsize=1)
def services():
    from azure.identity import ManagedIdentityCredential
    from azure.data.tables import TableClient
    from azure.storage.blob import BlobServiceClient
    from azure.storage.queue import QueueClient
    config=json.loads(os.environ['SPICE_CONTROL_CONFIG'])
    preflight(config)
    if os.environ.get('SPICE_EASY_AUTH_REQUIRED')!='true':
        raise ValueError('Platform authentication required')
    credential=ManagedIdentityCredential()
    account=os.environ['SPICE_STORAGE_ACCOUNT']
    if not account.isalnum() or not account.islower():
        raise ValueError('Invalid Azure Storage account')
    state=TableState(TableClient(endpoint='https://'+account+'.table.core.windows.net',table_name='control',credential=credential))
    jobs=AzureJobStore(state,queue=QueueClient(account_url='https://'+account+'.queue.core.windows.net',queue_name='jobs',credential=credential))
    assets=AssetStore(BlobServiceClient(account_url='https://'+account+'.blob.core.windows.net',credential=credential),'assets')
    # Exposed to the future orchestration composition root; never SQLite.
    ledger=AzureBudgetLedger(state,config['daily_cap_cents'])
    return CloudJobAPI(jobs,assets,config['devices'],config['operators']),ledger

def principal(headers):
    if os.environ.get('SPICE_EASY_AUTH_REQUIRED')!='true':
        return None
    try:
        raw=headers.get('X-MS-CLIENT-PRINCIPAL','')
        if len(raw)>16384:
            return None
        identity=json.loads(base64.b64decode(raw,validate=True))
        if identity.get('auth_typ')!='aad':
            return None
        claims={c['typ']:c['val'] for c in identity['claims']}
        tenant=claims.get('http://schemas.microsoft.com/identity/claims/tenantid') or claims.get('tid')
        subject=claims.get('http://schemas.microsoft.com/identity/claims/objectidentifier') or claims.get('oid')
        if tenant!=os.environ['SPICE_TENANT_ID'] or not subject:
            return None
        return {'subject':subject}
    except (ValueError,KeyError,TypeError):
        return None

@app.route(route='control/{operation}',methods=['POST'])
def control(req: func.HttpRequest) -> func.HttpResponse:
    identity=principal(req.headers)
    if identity is None:
        return func.HttpResponse(json.dumps({'error':'Authentication required'}),status_code=401,mimetype='application/json')
    try:
        if len(req.get_body())>65536:
            return func.HttpResponse('Request too large',status_code=413)
        api,_=services()
        status,body=api.handle(req.route_params['operation'],req.get_json(),identity)
    except (ValueError,KeyError):
        status,body=503,{'error':'Control plane configuration unavailable'}
    except Exception:
        # Never disclose storage credentials, SAS URLs, or exception details.
        status,body=503,{'error':'Control plane temporarily unavailable'}
    return func.HttpResponse(json.dumps(body,allow_nan=False),status_code=status,mimetype='application/json')
