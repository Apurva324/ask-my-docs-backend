# 📚 Ask My Docs — Production AI Backend

A production-grade RAG (Retrieval-Augmented Generation) API built with FastAPI, PostgreSQL, Redis, Celery, and Docker. Upload PDFs and ask questions — every answer is grounded with page citations.

## Live Demo
Frontend: https://askdocs.duckdns.org
API Docs: https://askdocs.duckdns.org/api/docs

## 🏗️ Architecture
User → FastAPI (JWT auth)

→ PostgreSQL (users, docs, chat history)

→ Celery + Redis (background PDF indexing)

→ Pinecone (vector search)

→ BM25 (keyword search)

→ Cross-encoder reranking

→ Groq LLaMA 3.1 (streaming answer)

## 🛠️ Tech Stack

| Layer | Tool |
|---|---|
| Backend | FastAPI, Python 3.11 |
| Database | PostgreSQL + SQLAlchemy |
| Auth | JWT (python-jose) |
| Vector DB | Pinecone (Serverless) |
| Keyword Search | BM25 (rank-bm25) |
| Embeddings | HuggingFace all-MiniLM-L6-v2 |
| Re-ranker | Cross-encoder ms-marco-MiniLM |
| LLM | Groq LLaMA 3.1 8B (streaming) |
| Cache + Queue | Redis |
| Background Tasks | Celery |
| Containerization | Docker + Docker Compose |
| Deployment | AWS EC2 |

## 🔄 RAG Pipeline

PDF Upload

→ Text extraction (pypdf)

→ Chunking (RecursiveCharacterTextSplitter)

→ Embedding (HuggingFace, 384 dims)

→ Storage (Pinecone + PostgreSQL)
Query

→ Hybrid retrieval (Pinecone vector + BM25 keyword)

→ Cross-encoder reranking (top 5 from 20 candidates)

→ Citation-enforced streaming answer (Groq LLaMA)

→ Chat history saved to PostgreSQL

## 📡 API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT token |

### Documents
| Method | Endpoint | Description |
|---|---|---|
| POST | `/documents/upload` | Upload and index PDF |
| GET | `/documents/` | List all documents |
| GET | `/documents/{id}` | Check indexing status |
| DELETE | `/documents/{id}` | Delete document |

### Chat
| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat/sessions/{document_id}` | Create chat session |
| POST | `/chat/ask/{session_id}` | Ask question (streaming) |
| GET | `/chat/sessions/{session_id}/messages` | Get chat history |

## ⚙️ Local Setup

### Prerequisites
- Docker + Docker Compose
- Pinecone API key
- Groq API key

### Run locally

```bash
git clone https://github.com/Apurva324/ask-my-docs-backend
cd ask-my-docs-backend
```

Create `.env` file:
DATABASE_URL=postgresql://postgres:password@db:5432/askdocs

REDIS_URL=redis://redis:6379

SECRET_KEY=your-secret-key

PINECONE_API_KEY=your-pinecone-key

GROQ_API_KEY=your-groq-key

Start all services:
```bash
docker-compose up --build
```

Open Swagger UI: http://localhost:8000/docs

## ✨ Key Features

- **Hybrid retrieval** — vector search + BM25 keyword search combined
- **Cross-encoder reranking** — scores top 5 from 20 candidates for accuracy
- **Citation enforcement** — every answer includes `[Page X]` references
- **Streaming responses** — token-by-token like ChatGPT
- **Multi-user support** — JWT auth with per-user document isolation
- **Background indexing** — Celery processes PDFs asynchronously
- **Chat history** — full conversation stored in PostgreSQL

## 🔗 Related

- **Streamlit Demo:** [Ask My Docs on HuggingFace](https://huggingface.co/spaces/Apurva324/ask-my-docs)
- **AutoGit CLI:** [Published on PyPI](https://pypi.org/project/ai-git/)


