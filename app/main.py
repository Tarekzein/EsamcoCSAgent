from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.embeddings import get_embedding_model
from app.core.retrieval import get_chroma_collection
from app.kb.routes import router as kb_router
from app.kb.database import init_db, ensure_root_category

log = logging.getLogger(__name__)

app = FastAPI(title="EsamcoChatbot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    ensure_root_category()
    get_chroma_collection()
    get_embedding_model()
    try:
        from app.core.groq_client import call_groq
        call_groq("مرحبا")
    except Exception as e:
        log.warning("Groq startup check failed (agent will still work for KB): %s", e)


static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)
app.include_router(kb_router)
