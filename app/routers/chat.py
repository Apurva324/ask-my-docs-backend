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
from app.services.cache_service import get_cached_answer, set_cached_answer

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

    # Cache lookup — only for questions with no prior conversation history.
    # Once there's history, the same question text can have a different
    # correct answer depending on what was discussed before (e.g. "what
    # about the second one?"), so caching there would risk serving a wrong
    # cached answer. Fresh, first-turn questions are the safe, high-value
    # case: those are exactly the ones that repeat across different users
    # asking the same doc the same thing.
    cached = None
    if not history_list:
        cached = get_cached_answer(document.pinecone_namespace, request.question)

    if cached is not None:
        async def generate_cached():
            yield cached["answer"]
            assistant_message = Message(
                session_id=session_id,
                role="assistant",
                content=cached["answer"],
                sources=cached["sources"]
            )
            db.add(assistant_message)
            db.commit()

        return StreamingResponse(generate_cached(), media_type="text/plain")

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

        # Populate cache for next time — only after a successful fresh-turn
        # generation, and only since we already checked history was empty.
        set_cached_answer(
            document.pinecone_namespace,
            request.question,
            full_answer,
            sources
        )

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