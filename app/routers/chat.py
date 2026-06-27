from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.document import Document
from app.models.session import ChatSession
from app.models.message import Message
from app.schemas.chat import ChatRequest, SessionResponse, MessageResponse
from app.dependencies import get_current_user
from app.services.rag_service import (
    get_pinecone_index,
    hybrid_retrieve,
    rerank
)
from app.services.llm_service import stream_answer, format_context

router = APIRouter()

@router.post("/sessions/{document_id}", response_model=SessionResponse)
def create_session(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify document belongs to user
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status != "indexed":
        raise HTTPException(status_code=400, detail="Document not indexed yet")

    session = ChatSession(
        user_id=current_user.id,
        document_id=document_id
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

@router.post("/ask/{session_id}")
async def ask_question(
    session_id: int,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get session
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get document
    document = db.query(Document).filter(
        Document.id == session.document_id
    ).first()

    # Get chat history
    history = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.created_at).all()

    history_list = [
        {"role": m.role, "content": m.content}
        for m in history[-4:]
    ]

    # Save user message
    user_message = Message(
        session_id=session_id,
        role="user",
        content=request.question
    )
    db.add(user_message)
    db.commit()

    # RAG pipeline
    index = get_pinecone_index()
    candidates = hybrid_retrieve(
        request.question,
        [],
        index,
        document.pinecone_namespace
    )
    top_docs = rerank(request.question, candidates)
    sources = [
        {"page": d.metadata.get("page", "?"), "text": d.page_content[:200]}
        for d in top_docs
    ]

    # Stream response
    async def generate():
        full_answer = ""
        async for chunk in stream_answer(request.question, top_docs, history_list):
            full_answer += chunk
            yield chunk

        # Save assistant message after streaming
        assistant_message = Message(
            session_id=session_id,
            role="assistant",
            content=full_answer,
            sources=sources
        )
        db.add(assistant_message)
        db.commit()

    return StreamingResponse(generate(), media_type="text/plain")

@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.created_at).all()
    return messages