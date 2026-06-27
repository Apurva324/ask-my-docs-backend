import time
import hashlib
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import CrossEncoder
from pinecone import Pinecone, ServerlessSpec
from pypdf import PdfReader
from app.config import (
    PINECONE_API_KEY,
    INDEX_NAME,
    EMBEDDING_DIM,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K_RETRIEVE,
    TOP_K_RERANK
)

# ── Models loaded once at startup ─────────────────────────────────────────────
embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# ── Pinecone ──────────────────────────────────────────────────────────────────
def get_pinecone_index():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    if INDEX_NAME not in [i.name for i in pc.list_indexes()]:
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
    return pc.Index(INDEX_NAME)

# ── Embedding ─────────────────────────────────────────────────────────────────
def embed_text(text: str) -> list[float]:
    return embedding_model.embed_documents([text])[0]

def embed_query(text: str) -> list[float]:
    return embedding_model.embed_query(text)

# ── PDF Processing ────────────────────────────────────────────────────────────
def extract_text_from_pdf(file_path: str) -> list[Document]:
    reader = PdfReader(file_path)
    docs = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            docs.append(Document(
                page_content=text,
                metadata={"page": i + 1}
            ))
    return docs

def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_documents(docs)

def doc_id(chunk: Document, idx: int) -> str:
    content = chunk.page_content[:200]
    return hashlib.md5(f"{content}{idx}".encode()).hexdigest()

# ── Retrieval ─────────────────────────────────────────────────────────────────
def hybrid_retrieve(
    query: str,
    chunks: list[Document],
    index,
    namespace: str
) -> list[Document]:
    query_vec = embed_query(query)

    for attempt in range(3):
        try:
            results = index.query(
                vector=query_vec,
                top_k=TOP_K_RETRIEVE,
                namespace=namespace,
                include_metadata=True
            )
            break
        except Exception as e:
            if attempt == 2:
                raise e
            time.sleep(1)

    vector_docs = [
        Document(
            page_content=m["metadata"]["text"],
            metadata={
                "page": m["metadata"].get("page", 0),
                "score": m["score"]
            }
        )
        for m in results["matches"]
    ]

    bm25_docs = []
    if chunks:
        bm25 = BM25Retriever.from_documents(chunks, k=TOP_K_RETRIEVE)
        bm25_docs = bm25.invoke(query)

    seen = set()
    merged = []
    for doc in vector_docs + bm25_docs:
        key = doc.page_content[:100]
        if key not in seen:
            seen.add(key)
            merged.append(doc)

    return merged

def rerank(query: str, docs: list[Document]) -> list[Document]:
    if not docs:
        return docs
    pairs = [(query, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in ranked[:TOP_K_RERANK]]