from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from app.config import GROQ_API_KEY

# ── LLM ──────────────────────────────────────────────────────────────────────
def get_llm(streaming: bool = False):
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.2,
        api_key=GROQ_API_KEY,
        streaming=streaming
    )

# ── Prompt ────────────────────────────────────────────────────────────────────
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

# ── Helpers ───────────────────────────────────────────────────────────────────
def format_context(docs: list[Document]) -> str:
    parts = []
    for doc in docs:
        page = doc.metadata.get("page", "?")
        parts.append(f"[Page {page}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)

def build_history_text(history: list) -> str:
    return "\n".join(
        f"{m['role']}: {m['content']}" for m in history[-4:]
    )

# ── Sync answer ───────────────────────────────────────────────────────────────
def answer_question(
    question: str,
    docs: list[Document],
    history: list
) -> str:
    llm = get_llm(streaming=False)
    context = format_context(docs)
    history_text = build_history_text(history)
    chain = CITATION_PROMPT | llm | StrOutputParser()
    return chain.invoke({
        "context": context,
        "question": question,
        "history": history_text
    })

# ── Async streaming answer ────────────────────────────────────────────────────
async def stream_answer(
    question: str,
    docs: list[Document],
    history: list
):
    llm = get_llm(streaming=True)
    context = format_context(docs)
    history_text = build_history_text(history)
    chain = CITATION_PROMPT | llm | StrOutputParser()

    async for chunk in chain.astream({
        "context": context,
        "question": question,
        "history": history_text
    }):
        yield chunk