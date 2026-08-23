# EsamcoCSAgent — Install & Run

RAG chatbot service for Esamco. FastAPI + ChromaDB (vector store) + Groq (LLM) +
sentence-transformers (embeddings, runs locally).

Answers are generated in Arabic from documents ingested into the vector store.

---

## 1. Requirements

| Thing | Version | Notes |
|---|---|---|
| Python | **3.12** | Not 3.13/3.14 — `torch 2.2.2` has no wheels for them, and `numpy<2` / `scipy<1.14` are pinned. |
| Groq API key | — | Free key from https://console.groq.com/keys |
| Disk | ~3 GB | torch + the embedding model download. |

No Ollama needed. The project used to run on a local Ollama model; commit
`00b9af8` migrated the LLM to Groq. The embedding model still runs locally.

Check your Python:

```bash
python3.12 --version   # must print 3.12.x
```

If you don't have it: `brew install python@3.12` (macOS).

---

## 2. Install

From the project root (`EsamcoCSAgent/`):

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Takes a few minutes — torch is a large download.

---

## 3. Configure

Create `.env` in the project root:

```bash
cp .env.example .env
```

Then **edit `.env`** so it contains your Groq key:

```dotenv
GROQ_API_KEY=gsk_your_key_here
```

> The shipped `.env.example` is stale — it only documents `OLLAMA_BASE_URL`,
> which the code no longer reads. `GROQ_API_KEY` is the only variable that
> matters, and the app **will not start** without it. See Troubleshooting.

Everything else (model names, chunk size, top-K, escalation keywords) is
hardcoded in [app/config.py](app/config.py), not env-driven:

- LLM: `llama-3.3-70b-versatile` (Groq)
- Embeddings: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, local)
- Chunking: 512 chars / 50 overlap, top-K 8

---

## 4. Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

**First start is slow (1–2 min).** The startup hook warms up three things
before serving: ChromaDB, the embedding model (downloaded from HuggingFace on
first run, then cached in `~/.cache/huggingface/`), and a test call to Groq.

Wait for:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8001
```

Then open **http://127.0.0.1:8001** for the chat UI.

Pick a port that doesn't collide with the Laravel backend — `8001` above
assumes Laravel is on `8000`.

---

## 5. Verify

```bash
curl http://127.0.0.1:8001/health
```

```json
{"status":"ok","model":"llama-3.3-70b-versatile","vector_count":320}
```

`vector_count` must be > 0, or the bot has no knowledge base to answer from
(see step 6).

Ask it something:

```bash
curl -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"ما هي شروط القبول؟"}'
```

```json
{"answer":"...","sources":[{"content":"...","score":0.92,"document":"testQa.pdf"}],"latency_ms":1234,"needs_human":false}
```

---

## 6. Loading documents

The repo already ships a populated `chroma_db/` (320 chunks from `testQa.pdf`),
so you can skip this unless you're adding documents or starting clean.

**PDF only** — `.docx` is rejected by the upload endpoint despite the parser
supporting it (`ALLOWED_EXTENSIONS = {".pdf"}`). Max 50 MB.

Via the API:

```bash
curl -X POST http://127.0.0.1:8001/upload -F "file=@yourdoc.pdf"
# → {"document_id":"...","chunks_count":42,"status":"ok"}
```

Or bulk-ingest every PDF in the project root (server does **not** need to be
running):

```bash
source .venv/bin/activate
python ingest_all.py
```

To wipe the knowledge base and start over: stop the server, `rm -rf chroma_db/`,
re-ingest. Ingesting the same file twice duplicates its chunks — there's no
dedupe.

---

## 7. API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Chat UI (Jinja2 page) |
| `GET` | `/health` | Status, model name, vector count |
| `POST` | `/chat` | `{"query": "..."}` → answer + sources |
| `POST` | `/upload` | multipart `file=` → ingests a PDF |

### The `needs_human` flag

`/chat` responses carry `needs_human: true` when the conversation should be
escalated to a live agent. It fires when:

- the query contains an escalation keyword (`خدمة العملاء`, `human`, `agent`, …)
- the model says it can't answer from the retrieved context
- retrieval returned nothing at all
- the LLM call errored

The consuming client (Laravel backend / chat widget) is responsible for acting
on it. Query limit: 500 chars.

---

## 8. Troubleshooting

**`groq.GroqError: The api_key client option must be set`**
No `GROQ_API_KEY` in `.env`. The Groq client is constructed at *import* time
([app/core/groq_client.py:4](app/core/groq_client.py#L4)), so this kills the
process before the server binds — it is not a runtime warning. Fix step 3.

**`ModuleNotFoundError: No module named 'groq'`**
Venv predates the Groq migration. Re-run `pip install -r requirements.txt`.

**Startup hangs ~1 min on first run, no output**
Normal — downloading the embedding model. Subsequent starts are fast.

**Server exits during startup with a Groq 401 / auth error**
Key is present but invalid. The `warmup()` hook in
[app/main.py:14-18](app/main.py#L14-L18) makes a real Groq call, so a bad key
fails the boot rather than the first request.

**`vector_count: 0`**
Empty vector store — every answer will be a generic fallback. See step 6.

**torch / numpy wheel build errors on install**
You're on Python 3.13+. Rebuild the venv with 3.12 (step 1).
