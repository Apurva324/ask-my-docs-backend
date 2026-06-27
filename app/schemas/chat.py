from pydantic import BaseModel
from datetime import datetime

class ChatRequest(BaseModel):
    question: str
    session_id: int | None = None

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list | None
    created_at: datetime

    class Config:
        from_attributes = True

class SessionResponse(BaseModel):
    id: int
    document_id: int
    created_at: datetime

    class Config:
        from_attributes = True