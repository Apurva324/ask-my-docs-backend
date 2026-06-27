from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id                  = Column(Integer, primary_key=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename            = Column(String, nullable=False)
    s3_url              = Column(String)
    pinecone_namespace  = Column(String)
    status              = Column(String, default="processing")
    # processing → indexed → failed
    created_at          = Column(DateTime, default=func.now())

    # Relationships
    owner    = relationship("User", back_populates="documents")
    sessions = relationship("ChatSession", back_populates="document")