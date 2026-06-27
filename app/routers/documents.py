import hashlib
import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.document import Document
from app.schemas.document import DocumentResponse, DocumentStatusResponse
from app.dependencies import get_current_user
from app.tasks.indexing import index_document_task

router = APIRouter()

# Written under /app/tmp (not /tmp) so the celery_worker container can see
# the same file — both services share the `.:/app` bind mount in
# docker-compose.yml, but NOT the container-local /tmp filesystem.
TMP_DIR = "/app/tmp"


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    namespace = hashlib.md5(
        f"{current_user.id}{file.filename}".encode()
    ).hexdigest()[:12]

    contents = await file.read()
    os.makedirs(TMP_DIR, exist_ok=True)
    tmp_path = f"{TMP_DIR}/{namespace}_{file.filename}"
    with open(tmp_path, "wb") as f:
        f.write(contents)

    document = Document(
        user_id=current_user.id,
        filename=file.filename,
        pinecone_namespace=namespace,
        status="processing"
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Hand off extraction/chunking/embedding/upserting to the Celery worker
    # instead of blocking this request.
    index_document_task.delay(tmp_path, namespace, document.id)

    return document


@router.get("/", response_model=list[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    documents = db.query(Document).filter(
        Document.user_id == current_user.id
    ).all()
    return documents


@router.get("/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    db.delete(document)
    db.commit()
    return {"message": "Document deleted successfully"}