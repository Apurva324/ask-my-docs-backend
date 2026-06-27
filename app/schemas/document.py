from pydantic import BaseModel
from datetime import datetime

class DocumentResponse(BaseModel):
    id: int
    filename: str
    status: str
    pinecone_namespace: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentStatusResponse(BaseModel):
    id: int
    filename: str
    status: str