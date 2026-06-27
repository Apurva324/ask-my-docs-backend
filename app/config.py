import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "ask-my-docs"
EMBEDDING_DIM = 384

# Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# AWS
# AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
# AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
# AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
# AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# RAG
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K_RETRIEVE = 20
TOP_K_RERANK = 5