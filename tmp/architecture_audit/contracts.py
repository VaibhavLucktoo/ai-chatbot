"""In-memory contract probes, no DB, real credentials, model calls or file writes to app state."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Backend'))

import httpx
from fastapi import FastAPI
from app.api.v1.router import api_router
from app.api.v1.chat import get_db_session
from app.api.v1.widgets import page_router
from app.core.middleware import LocalWorkspaceMiddleware
from app.core.local_access import is_local_scope
from app.schemas.widgets import WidgetWrite, website_origin


async def main():
    app = FastAPI()
    app.state.database = SimpleNamespace()
    app.state.admin_token = 'audit-token'
    app.include_router(api_router, prefix='/v1')
    app.include_router(page_router)
    async def isolated_session():
        yield SimpleNamespace()
    app.dependency_overrides[get_db_session] = isolated_session
    app.add_middleware(LocalWorkspaceMiddleware, state=app.state, max_active_requests=4)
    spec = app.openapi()
    operations = []
    for path, verbs in spec['paths'].items():
        for method, operation in verbs.items():
            if method not in {'get', 'post', 'put', 'patch', 'delete'}:
                continue
            content = operation.get('requestBody', {}).get('content', {})
            operations.append({'method': method.upper(), 'path': path, 'id': operation['operationId'],
                'body': {kind: item.get('schema') for kind, item in content.items()},
                'parameters': operation.get('parameters', []), 'responses': operation['responses'],
                'security': operation.get('security', [])})
    results = {'operations': operations, 'probes': {}}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app, raise_app_exceptions=False, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1')
    async with client:
        malformed = await client.post('/v1/chat', json={'question': '', 'top_k': 'five'})
        results['probes']['default_validation'] = {'status': malformed.status_code, 'body': malformed.json()}
        configuration = await client.put('/v1/admin/assistants/' + str(uuid4()) + '/widget',
            headers={'X-Admin-Token': 'audit-token'}, json={'requests_per_minute': 'five'})
        results['probes']['configuration_validation'] = {'status': configuration.status_code, 'body': configuration.json()}
        class BadDatabase:
            def transaction(self):
                raise TimeoutError('audit failure')
        app.state.database = BadDatabase()
        jobs = await client.get('/v1/documents/jobs/' + str(uuid4()))
        catalog = await client.get('/v1/documents')
        results['probes']['database_timeout_statuses'] = {'job_status': jobs.status_code, 'catalog_status': catalog.status_code,
            'job_content_type': jobs.headers.get('content-type'), 'catalog_body': catalog.json()}
        cold = await client.get('/v1/health', headers={'Content-Length': '-1'})
        results['probes']['early_error_headers'] = {name: cold.headers.get(name) for name in ('x-request-id', 'cache-control', 'x-content-type-options')}
        valid = await client.get('/v1/health')
        results['probes']['normal_headers'] = {name: valid.headers.get(name) for name in ('x-request-id', 'cache-control', 'x-content-type-options')}
    results['probes']['coerced_boolean'] = WidgetWrite(enabled='false').enabled
    long_origin = 'https://' + '.'.join(['a' * 60] * 6)
    accepted = WidgetWrite(allowed_origins=[long_origin])
    results['probes']['long_allowed_origin'] = {'length': len(accepted.allowed_origins[0]), 'accepted': True}
    results['probes']['local_host_authority'] = {host: is_local_scope({'headers': [(b'host', host.encode())], 'client': ('127.0.0.1', 4)})
        for host in ('127.0.0.1', 'user@127.0.0.1', '127.0.0.1/path', '127.0.0.1:garbage')}
    results['probes']['schema_types'] = {name: spec['components']['schemas'].get(name, {}) for name in ('DocumentJobResponse', 'VisitorSession', 'AnalyticsResponse')}
    destination = ROOT / 'docs' / 'architecture-contract-probes-2026-10-14.json'
    destination.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps({'operation_count': len(operations), 'operations': [item['method'] + ' ' + item['path'] for item in operations],
                      'probes': {key: value for key, value in results['probes'].items() if key != 'schema_types'}}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
