"""Read-only database evidence; never exports document text or credentials."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "Backend"))

import psycopg
from psycopg import sql
from app.core.config import get_settings
from app.storage.models import Base


def audit(database_name=None):
    settings = get_settings()
    if database_name is not None:
        if not database_name.startswith("restore_"):
            raise ValueError("Only a restore_* database may override the configured target")
        settings = settings.model_copy(update={"postgres_db": database_name})
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "read_only": True}
    with psycopg.connect(host=settings.db_host, port=settings.db_port,
                          dbname=settings.postgres_db, user=settings.postgres_user,
                          password=settings.postgres_password.get_secret_value(),
                          connect_timeout=5,
                          options="-c default_transaction_read_only=on -c statement_timeout=15000") as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            def query(statement):
                cursor.execute(statement)
                columns = [item.name for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

            report["server"] = query("SELECT current_setting('server_version') AS postgres_version, (SELECT extversion FROM pg_extension WHERE extname='vector') AS pgvector_version")
            report["migration"] = query("SELECT version_num FROM public.alembic_version")
            report["table_counts"] = {}
            fingerprints = {}
            for name in sorted(Base.metadata.tables):
                cursor.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(name)))
                report["table_counts"][name] = cursor.fetchone()[0]
                # Canonical row text covers all fields without exporting any values.
                cursor.execute(sql.SQL("SELECT md5(row_to_json(t)::text) FROM public.{} AS t ORDER BY 1").format(sql.Identifier(name)))
                digest = sha256()
                for row in cursor:
                    digest.update(row[0].encode("ascii"))
                fingerprints[name] = digest.hexdigest()
            report["table_fingerprints"] = fingerprints
            report["document_states"] = query("SELECT status, active, count(*) AS documents, count(original_pdf) AS retained_pdfs, count(processing_metadata) AS processing_metadata_rows, coalesce(sum(octet_length(original_pdf)),0) AS pdf_bytes FROM public.documents GROUP BY status,active ORDER BY status,active")
            report["embeddings"] = query("SELECT embedding_space, count(*) AS chunks, min(vector_dims(embedding)) AS min_dimensions, max(vector_dims(embedding)) AS max_dimensions, min(vector_norm(embedding)) AS min_norm, max(vector_norm(embedding)) AS max_norm, count(*) FILTER (WHERE abs(vector_norm(embedding)-1)>0.00001) AS non_normalized, avg(pg_column_size(embedding)) AS average_stored_vector_bytes, sum(octet_length(content)) AS text_bytes FROM public.document_chunks GROUP BY embedding_space")
            report["indexes"] = query("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname")
            report["constraints"] = query("SELECT c.relname AS table_name, k.conname AS name, k.contype AS type, k.convalidated AS validated, pg_get_constraintdef(k.oid) AS definition FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,k.conname")
            report["column_types"] = query("SELECT c.relname AS table_name,a.attname AS column_name,format_type(a.atttypid,a.atttypmod) AS data_type,a.attnotnull AS not_null FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum")
            report["storage"] = query("SELECT relname AS table_name, pg_table_size(relid) AS table_bytes,pg_indexes_size(relid) AS index_bytes,pg_total_relation_size(relid) AS total_bytes FROM pg_statio_user_tables WHERE schemaname='public' ORDER BY relname")
            checks = {
                "orphan_chunks": "SELECT count(*) FROM public.document_chunks c LEFT JOIN public.documents d ON d.id=c.document_id WHERE d.id IS NULL",
                "ready_documents_without_chunks": "SELECT count(*) FROM public.documents d WHERE status='ready' AND NOT EXISTS (SELECT 1 FROM public.document_chunks c WHERE c.document_id=d.id)",
                "chunks_on_unfinished_documents": "SELECT count(*) FROM public.document_chunks c JOIN public.documents d ON d.id=c.document_id WHERE d.status<>'ready'",
                "chunks_beyond_page_count": "SELECT count(*) FROM public.document_chunks c JOIN public.documents d ON d.id=c.document_id WHERE c.page_number>d.page_count",
                "non_contiguous_chunk_positions": "SELECT count(*) FROM (SELECT document_id FROM public.document_chunks GROUP BY document_id HAVING min(chunk_index)<>0 OR max(chunk_index)<>count(*)-1) x",
                "duplicate_document_hashes": "SELECT count(*) FROM (SELECT content_sha256 FROM public.documents GROUP BY content_sha256 HAVING count(*)>1) x",
                "expired_conversations_still_stored": "SELECT count(*) FROM public.chat_conversations WHERE expires_at<=now()",
                "expired_widget_sessions_still_stored": "SELECT count(*) FROM public.widget_sessions WHERE expires_at<=now()",
                "invalid_conversation_key_hashes": "SELECT count(*) FROM public.chat_conversations WHERE owner_key_hash !~ '^[a-f0-9]{64}$'",
                "invalid_widget_token_hashes": "SELECT count(*) FROM public.widget_sessions WHERE token_hash !~ '^[a-f0-9]{64}$'",
                "dangling_assistant_conversations": "SELECT count(*) FROM public.chat_conversations c LEFT JOIN public.assistants a ON a.id=c.assistant_id WHERE c.assistant_id IS NOT NULL AND a.id IS NULL",
                "widget_sessions_without_conversations": "SELECT count(*) FROM public.widget_sessions s LEFT JOIN public.chat_conversations c ON c.id=s.conversation_id WHERE c.id IS NULL",
            }
            report["integrity"] = {}
            for name, statement in checks.items():
                cursor.execute(statement)
                report["integrity"][name] = cursor.fetchone()[0]
            cursor.execute("SELECT original_pdf,content_sha256 FROM public.documents WHERE original_pdf IS NOT NULL")
            retained = mismatches = 0
            for data, expected in cursor:
                retained += 1
                mismatches += sha256(bytes(data)).hexdigest() != expected
            report["source_hashes"] = {"retained_pdfs_checked": retained, "mismatches": mismatches}
            report["conversation_bounds"] = query("SELECT coalesce(max(json_array_length(history)),0) AS max_turns, coalesce(max(octet_length(history::text)),0) AS max_json_bytes FROM public.chat_conversations")
            report["other_schemas"] = query("SELECT nspname AS schema_name FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%' ORDER BY nspname")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database")
    args = parser.parse_args()
    result = audit(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("server", "migration", "table_counts", "document_states", "embeddings", "integrity", "source_hashes", "conversation_bounds", "other_schemas")}, indent=2, default=str))
    print("Saved:", args.output.resolve())
