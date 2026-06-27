from app.celery_app import celery_app
from app.services.rag_service import (
    extract_text_from_pdf,
    chunk_documents,
    embed_text,
    doc_id,
    get_pinecone_index
)
from app.database import SessionLocal
from app.models.document import Document as DocumentModel

@celery_app.task
def index_document_task(file_path: str, namespace: str, document_id: int):
    try:
        # Extract and chunk
        docs = extract_text_from_pdf(file_path)
        chunks = chunk_documents(docs)

        # Embed and store in Pinecone
        index = get_pinecone_index()
        vectors = []
        for i, chunk in enumerate(chunks):
            embedding = embed_text(chunk.page_content)
            vectors.append({
                "id": doc_id(chunk, i),
                "values": embedding,
                "metadata": {
                    "text": chunk.page_content,
                    "page": chunk.metadata.get("page", 0)
                }
            })
            if len(vectors) == 50:
                index.upsert(vectors=vectors, namespace=namespace)
                vectors = []
        if vectors:
            index.upsert(vectors=vectors, namespace=namespace)

        # Update document status in PostgreSQL
        db = SessionLocal()
        doc = db.query(DocumentModel).filter(
            DocumentModel.id == document_id
        ).first()
        if doc:
            doc.status = "indexed"
            db.commit()
        db.close()

        return {"status": "done", "chunks": len(chunks)}

    except Exception as e:
        # Update status to failed
        db = SessionLocal()
        doc = db.query(DocumentModel).filter(
            DocumentModel.id == document_id
        ).first()
        if doc:
            doc.status = "failed"
            db.commit()
        db.close()
        raise e