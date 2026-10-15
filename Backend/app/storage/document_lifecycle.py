"""Document activation and deletion transactions."""

from sqlalchemy import delete, update

from app.storage.models import Document


async def set_document_activation(database, document_id, active):
    async with database.transaction() as connection:
        result = await connection.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.status == "ready",
            )
            .values(active=active)
        )
    return result.rowcount


async def delete_document(database, document_id):
    async with database.transaction() as connection:
        result = await connection.execute(
            delete(Document).where(Document.id == document_id)
        )
    return result.rowcount
