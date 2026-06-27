from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Message(Base):
    __tablename__ = "messages"

    id          = Column(Integer, primary_key=True, index=True)
    session_id  = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role        = Column(String, nullable=False)  # "user" or "assistant"
    content     = Column(Text, nullable=False)
    sources     = Column(JSON, nullable=True)     # stores page citations
    tokens_used = Column(Integer, nullable=True)
    created_at  = Column(DateTime, default=func.now())

    # Relationship
    session = relationship("ChatSession", back_populates="messages")