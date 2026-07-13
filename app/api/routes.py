import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB, MAX_QUERY_LENGTH
from app.core.ingestion import ingest_file
from app.core.retrieval import answer_query
import chromadb
from app.config import CHROMA_DB_DIR, COLLECTION_NAME, LLM_MODEL

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


class ChatRequest(BaseModel):
    query: str


@router.get("/health")
def health():
    try:
        client = chromadb.PersistentClient(str(CHROMA_DB_DIR))
        collection = client.get_or_create_collection(COLLECTION_NAME)
        count = collection.count()
        return {"status": "ok", "model": LLM_MODEL, "vector_count": count}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_FILE_SIZE_MB}MB limit")

    save_path = UPLOADS_DIR / f"{uuid.uuid4()}{ext}"
    with open(save_path, "wb") as f:
        f.write(contents)

    try:
        result = ingest_file(str(save_path))
        return result
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {str(e)}")
    finally:
        os.remove(save_path)


@router.post("/chat")
def chat(req: ChatRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "query is required")
    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(400, f"query exceeds {MAX_QUERY_LENGTH} characters")
    try:
        return answer_query(query)
    except Exception:
        return {
            "answer": "عذراً، حدث خطأ. هل تريد التحدث مع خدمة العملاء؟",
            "sources": [],
            "latency_ms": 0,
            "needs_human": True,
        }


@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="chat.html")
