import os
import time
import tempfile
import hashlib
import streamlit as st
from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import CrossEncoder
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
INDEX_NAME         = "ask-my-docs"
EMBEDDING_DIM      = 384
CHUNK_SIZE         = 800
CHUNK_OVERLAP      = 150
TOP_K_RETRIEVE     = 20
TOP_K_RERANK       = 5

embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# ── Clients ──────────────────────────────────────────────────────────────────
@st.cache_resource
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

@st.cache_resource
def get_llm():
    """Groq — used ONLY for answer generation (1 call per question)."""
    return ChatGroq(model="llama-3.1-8b-instant", temperature=0.2, api_key=GROQ_API_KEY)


@st.cache_resource
def get_cross_encoder():
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# ── Embedding ────────────────────────────────────────────────────────────────
def embed_text(text: str) -> list[float]:
    return embedding_model.embed_documents([text])[0]

def embed_query(text: str) -> list[float]:
    return embedding_model.embed_query(text)

# ── PDF Processing ───────────────────────────────────────────────────────────
def extract_text_from_pdf(file) -> list[Document]:
    reader = PdfReader(file)
    docs = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            docs.append(Document(
                page_content=text,
                metadata={"page": i + 1, "source": file.name}
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

# ── Ingest ───────────────────────────────────────────────────────────────────
def ingest_pdf(uploaded_file, index) -> tuple[list[Document], str]:
    namespace = hashlib.md5(uploaded_file.name.encode()).hexdigest()[:12]

    stats = index.describe_index_stats()
    if namespace in stats.get("namespaces", {}):
        st.info(f"📦 '{uploaded_file.name}' already indexed — loading from Pinecone.")
        return None, namespace

    with st.spinner(f"Reading and chunking '{uploaded_file.name}'..."):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            docs = extract_text_from_pdf(f)
        chunks = chunk_documents(docs)

    with st.spinner(f"Embedding {len(chunks)} chunks..."):
        vectors = []
        for i, chunk in enumerate(chunks):
            embedding = embed_text(chunk.page_content)
            vectors.append({
                "id": doc_id(chunk, i),
                "values": embedding,
                "metadata": {
                    "text": chunk.page_content,
                    "page": chunk.metadata.get("page", 0),
                    "source": chunk.metadata.get("source", "")
                }
            })
            if len(vectors) == 50:
                index.upsert(vectors=vectors, namespace=namespace)
                vectors = []
        if vectors:
            index.upsert(vectors=vectors, namespace=namespace)

    st.success(f"Indexed {len(chunks)} chunks from '{uploaded_file.name}'")
    return chunks, namespace

# ── Retrieval ────────────────────────────────────────────────────────────────
def hybrid_retrieve(query: str, chunks: list[Document], index, namespace: str) -> list[Document]:
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
            metadata={"page": m["metadata"].get("page", 0), "source": m["metadata"].get("source", ""), "score": m["score"]}
        )
        for m in results["matches"]
    ]

    if chunks:
        bm25 = BM25Retriever.from_documents(chunks, k=TOP_K_RETRIEVE)
        bm25_docs = bm25.invoke(query)
    else:
        bm25_docs = []

    seen = set()
    merged = []
    for doc in vector_docs + bm25_docs:
        key = doc.page_content[:100]
        if key not in seen:
            seen.add(key)
            merged.append(doc)

    return merged

def rerank(query: str, docs: list[Document], cross_encoder) -> list[Document]:
    if not docs:
        return docs
    pairs = [(query, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in ranked[:TOP_K_RERANK]]


# ── Prompt ───────────────────────────────────────────────────────────────────
CITATION_PROMPT = PromptTemplate(
    template="""You are a precise research assistant. Answer ONLY using the provided context chunks below.

STRICT RULES:
1. Every claim you make MUST be supported by a chunk — cite it as [Page X].
2. If the answer is not in the context, say "I could not find this in the provided documents."
3. Do NOT use any external knowledge.
4. Be concise and structured.

Conversation History (for context only):
{history}

Context Chunks:
{context}

Question: {question}

Answer (with citations like [Page X]):""",
    input_variables=["context", "question", "history"]
)

def format_context(docs: list[Document]) -> str:
    parts = []
    for doc in docs:
        page = doc.metadata.get("page", "?")
        parts.append(f"[Page {page}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)

def answer_question(question: str, docs: list[Document], llm, history: list) -> str:
    context = format_context(docs)
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history[-4:]
    )
    chain = CITATION_PROMPT | llm | StrOutputParser()
    return chain.invoke({"context": context, "question": question, "history": history_text})

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ask My Docs", page_icon="📚", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1a1a2e; }
    .sub-header { color: #666; margin-bottom: 2rem; }
    .source-badge {
        display: inline-block; background: #e8f4fd; color: #1a73e8;
        border-radius: 12px; padding: 2px 10px; font-size: 0.8rem;
        margin: 2px; border: 1px solid #b3d4f5;
    }
    .citation-box {
        background: #f8f9fa; border-left: 4px solid #1a73e8;
        padding: 12px 16px; border-radius: 0 8px 8px 0;
        margin: 8px 0; font-size: 0.9rem; color: #1a1a1a;
    }
    .stButton > button {
        background: #1a73e8; color: white;
        border: none; border-radius: 8px;
        padding: 0.5rem 1.5rem; font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-header">📚 Ask My Docs</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Upload research papers or any PDFs and ask questions — every answer is grounded with citations.</p>', unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────────────
for key, default in {
    "chunks": [],
    "namespace": None,
    "history": [],
    "current_file": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📄 Upload Document")
    uploaded_file = st.file_uploader("Choose a PDF", type=["pdf"])

    if uploaded_file:
        if uploaded_file.name != st.session_state.current_file:
            st.session_state.history = []
            st.session_state.chunks = []
            st.session_state.namespace = None
            st.session_state.current_file = uploaded_file.name

        index = get_pinecone_index()

        if st.button("Index Document"):
            chunks, namespace = ingest_pdf(uploaded_file, index)
            st.session_state.namespace = namespace
            if chunks:
                st.session_state.chunks = chunks
            else:
                results = index.query(
                    vector=[0.0] * EMBEDDING_DIM,
                    top_k=1000,
                    namespace=namespace,
                    include_metadata=True
                )
                st.session_state.chunks = [
                    Document(
                        page_content=m["metadata"]["text"],
                        metadata={"page": m["metadata"].get("page", 0)}
                    )
                    for m in results["matches"]
                ]

    st.divider()

    st.divider()
    st.markdown("**Pipeline**")
    st.markdown("Pinecone vector search")
    st.markdown("BM25 keyword search")
    st.markdown("Cross-encoder re-ranking")
    st.markdown("Groq `llama-3.1-8b-instant` ← answers only")
    st.markdown("Citation enforcement")

    if st.button("Clear Chat"):
        st.session_state.history = []
        st.rerun()

# ── Main Chat ─────────────────────────────────────────────────────────────────
if not st.session_state.namespace:
    st.info("Upload a PDF and click **Index Document** to get started.")
else:
    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and "sources" in msg:
                with st.expander("📎 Source chunks used"):
                    for src in msg["sources"]:
                        st.markdown(
                            f'<div class="citation-box">'
                            f'<span class="source-badge">Page {src["page"]}</span>'
                            f'<br>{src["text"][:300]}...</div>',
                            unsafe_allow_html=True
                        )

    question = st.chat_input("Ask anything about your document...")

    if question:
        st.session_state.history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("🔍 Retrieving → re-ranking → answering..."):
                index        = get_pinecone_index()
                llm          = get_llm()
                cross_encoder = get_cross_encoder()

                candidates = hybrid_retrieve(
                    question,
                    st.session_state.chunks,
                    index,
                    st.session_state.namespace
                )
                top_docs = rerank(question, candidates, cross_encoder)
                answer   = answer_question(question, top_docs, llm, st.session_state.history)

            st.markdown(answer)

            sources = [{"page": d.metadata.get("page", "?"), "text": d.page_content} for d in top_docs]
            with st.expander("Source chunks used"):
                for src in sources:
                    st.markdown(
                        f'<div class="citation-box">'
                        f'<span class="source-badge">Page {src["page"]}</span>'
                        f'<br>{src["text"][:300]}...</div>',
                        unsafe_allow_html=True
                    )


        st.session_state.history.append({
            "role":    "assistant",
            "content": answer,
            "sources": sources,
        })