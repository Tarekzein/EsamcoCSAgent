# EsamcoChatbot — Project Map

## Tech Stack

| Layer | Choice | Version | License |
|-------|--------|---------|---------|
| **Backend** | FastAPI | latest | MIT |
| **Templates** | Jinja2Templates | — | BSD |
| **LLM** | Qwen3 4B via Ollama | latest | Apache 2.0 |
| **Embeddings** | `arabic-gte-multilingual-base-100k` | — | Apache 2.0 |
| **Vector DB** | ChromaDB | 1.5.9 | Apache 2.0 |
| **Doc Parser** | PyMuPDF + python-docx | latest | AGPL / MIT |
| **Chunking** | LangChain RecursiveCharacterTextSplitter | latest | MIT |

## System Flow

```
Upload PDF/DOCX → extract text → chunk (512/50)
  → arabic-gte embeddings (768d) → ChromaDB.add()

POST /chat {"query":"..."}
  → same embedding → ChromaDB search(k=5)
    → Ollama qwen3:4b (context + query → answer)
      → return {"answer","sources","latency_ms"}
```

## Architecture

```
EsamcoChatbot/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app entry point
│   ├── config.py              # Paths, model names, chunk sizes
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py          # POST /upload, POST /chat, GET /, GET /health
│   ├── core/
│   │   ├── __init__.py
│   │   ├── ingestion.py       # PDF/DOCX → chunk → embed → ChromaDB
│   │   ├── retrieval.py       # Query → ChromaDB → LLM → answer
│   │   └── embeddings.py      # SentenceTransformer wrapper
│   ├── templates/
│   │   └── chat.html          # Minimal browser UI
│   └── static/
│       └── style.css
├── chroma_db/                 # Persisted vector store (gitignored)
├── uploads/                   # Temp uploads (gitignored)
├── requirements.txt
├── .gitignore
└── PROJECT_MAP.md
```

## API Contract (for Laravel)

### POST /chat
```json
// Request
{"query": "ما هي شروط القبول؟"}

// Response 200
{
  "answer": "شروط القبول هي ...",
  "sources": [
    {"content": "نص المستند...", "score": 0.92, "document": "file.pdf"},
    {"content": "نص آخر...", "score": 0.85, "document": "file.pdf"}
  ],
  "latency_ms": 1234
}
```

### POST /upload
```
multipart/form-data: file=document.pdf
→ {"document_id": "...", "chunks_count": 42, "status": "ok"}
```

### GET /health
```
→ {"status": "ok", "model": "qwen3:4b", "vector_count": 42}
```

## Orphans & Pending

- [ ] Install Ollama + pull qwen3:4b
- [ ] Create and activate virtualenv
- [ ] Run `pip install -r requirements.txt`
- [ ] Start app: `uvicorn app.main:app --reload`
- [ ] Upload test documents
- [ ] Verify Arabic + English Q&A
- [ ] Integrate with Laravel

## Milestones

| # | Goal | Verification |
|---|------|-------------|
| M1 | Ollama ready | `ollama run qwen3:4b` answers in Arabic |
| M2 | Ingestion works | Upload Arabic PDF → chunks in ChromaDB |
| M3 | Chat works | `curl POST /chat` returns Arabic answer + sources |
| M4 | UI accessible | Browser shows chat UI at `GET /` |
| M5 | Laravel integration | Laravel calls `/chat`, stores in MySQL |
pip install -r requirements.txt   # installs sentence-transformers
uvicorn app.main:app --reload     # startup will warm up all models