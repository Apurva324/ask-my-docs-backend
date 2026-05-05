---
title: Ask My Docs
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.35.0
app_file: main.py
pinned: false
---

# 📚 Ask My Docs

A RAG (Retrieval-Augmented Generation) powered document QA app — upload any PDF and ask questions. Every answer is grounded with citations from the document.

## 🚀 Features

- **Hybrid Retrieval** — combines Pinecone vector search + BM25 keyword search
- **Cross-Encoder Re-ranking** — re-ranks candidates for highest relevance
- **Citation-enforced answers** — every claim is backed by a `[Page X]` reference
- **Conversation memory** — maintains recent chat history for context
- **Fast LLM** — powered by Groq's `llama-3.1-8b-instant`

## 🛠️ Tech Stack

| Layer | Tool |
|---|---|
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector Store | Pinecone (Serverless) |
| Keyword Search | BM25 via LangChain |
| Re-ranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| LLM | Groq — `llama-3.1-8b-instant` |
| Frontend | Streamlit |

## ⚙️ Setup (Local)

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in the root directory:
```env
PINECONE_API_KEY=your_pinecone_api_key
GROQ_API_KEY=your_groq_api_key
```

### 4. Run the app
```bash
streamlit run main.py
```

## ☁️ Deploying on Hugging Face Spaces

1. Create a new Space on [huggingface.co/spaces](https://huggingface.co/spaces) with **Streamlit** as the SDK
2. Add your secrets under **Settings → Variables and Secrets**:
   - `PINECONE_API_KEY`
   - `GROQ_API_KEY`
3. Push this repo to the Space:
```bash
git remote add space https://huggingface.co/spaces/YOUR_HF_USERNAME/ask-my-docs
git push space main
```

## 📖 How to Use

1. Upload a PDF using the sidebar
2. Click **Index Document** — chunks are embedded and stored in Pinecone
3. Ask any question in the chat input
4. View cited answers and expand **Source Chunks** to see the exact passages used

## 🔑 API Keys Required

- **Pinecone** — [app.pinecone.io](https://app.pinecone.io) (free tier works)
- **Groq** — [console.groq.com](https://console.groq.com) (free tier works)