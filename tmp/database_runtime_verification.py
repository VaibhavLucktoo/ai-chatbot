"""Exercise cached embeddings and local read APIs without changing saved rows."""
import asyncio
import json
import math
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "Backend"))

import httpx
import psycopg
from pgvector.psycopg import register_vector
from pydantic import SecretStr
from app.core.config import get_settings
from app.main import create_app
from app.providers.embeddings import get_embedding_provider
from app.services.credential_vault import CredentialVault
from app.services.retrieval import retrieve_chunks
from run import create_event_loop


async def verify():
    settings = get_settings()
    with psycopg.connect(host=settings.db_host, port=settings.db_port,
                          dbname=settings.postgres_db, user=settings.postgres_user,
                          password=settings.postgres_password.get_secret_value(),
                          connect_timeout=5,
                          options="-c default_transaction_read_only=on -c statement_timeout=15000") as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute("SELECT content,embedding FROM public.document_chunks ORDER BY id")
            chunks = cursor.fetchall()
            cursor.execute("SELECT id,provider,encrypted_api_key FROM public.provider_connections")
            credentials = cursor.fetchall()
    vault = CredentialVault(settings)
    decryption_successes = 0
    for identifier, provider, encrypted in credentials:
        key = vault.decrypt(encrypted, provider=provider, connection_id=str(identifier))
        assert isinstance(key, SecretStr) and key.get_secret_value()
        decryption_successes += 1

    app = create_app()
    # Only suppress ingestion recovery during this read-only inspection.
    app.state.widget_only = True
    report = {"provider_credentials_checked": len(credentials),
              "provider_credentials_decryptable": decryption_successes}
    async with app.router.lifespan_context(app):
        provider = get_embedding_provider()
        distances = []
        for start in range(0, len(chunks), 32):
            batch = chunks[start:start + 32]
            regenerated = await provider.embed_documents([text for text, _ in batch])
            for (_, stored), fresh in zip(batch, regenerated, strict=True):
                stored_values = [float(value) for value in stored.to_list()]
                cosine = sum(a*b for a,b in zip(stored_values,fresh,strict=True)) / (math.hypot(*stored_values)*math.hypot(*fresh))
                distances.append(max(0.0, 1.0 - cosine))
        report["vector_reproduction"] = {
            "checked": len(distances),
            "max_cosine_distance": max(distances, default=None),
            "mismatches_above_0_00001": sum(value > 0.00001 for value in distances),
        }
        report["http_statuses"] = {}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            for path in ("/v1/health", "/v1/ready", "/admin", "/v1/admin/status", "/v1/admin/documents", "/v1/admin/metrics"):
                response = await client.get(path, headers={"X-Admin-Token": app.state.admin_token})
                report["http_statuses"][path] = response.status_code
                response.raise_for_status()
            response = await client.post("/v1/documents/search", json={"query": "document information", "top_k": 5})
            response.raise_for_status()
            report["http_statuses"]["POST /v1/documents/search"] = response.status_code
            report["search_result_count"] = len(response.json()["results"])
        if chunks:
            sample = chunks[0][0][:300]
            results = await retrieve_chunks(app.state.database, provider, sample, top_k=5)
            assert results.chunks, "Stored-content retrieval returned no results"
            report["stored_content_retrieval"] = {"results":len(results.chunks), "all_distances_finite": all(math.isfinite(item.cosine_distance) for item in results.chunks)}
    return report


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        report = runner.run(verify())
    destination = WORKSPACE / "output" / "database-runtime-verification-2026-10-15.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Saved:", destination)
