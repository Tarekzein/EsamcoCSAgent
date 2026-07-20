from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.embeddings import get_embedding_model
from app.core.retrieval import get_chroma_collection
from app.core.groq_client import call_groq

app = FastAPI(title="EsamcoChatbot", version="1.0.0")


@app.on_event("startup")
def warmup():
    get_chroma_collection()
    get_embedding_model()
    call_groq("مرحبا")


static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)
