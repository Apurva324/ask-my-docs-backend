from fastapi import FastAPI
from app.database import engine, Base
import app.models
from app.routers import auth, documents, chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ask My Docs API")

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])

@app.get("/")
def health_check():
    return {"status": "running", "project": "Ask My Docs"}