import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

from app.kb import database as db
from app.config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB
from app.core.ingestion import extract_text, chunk_text, get_chroma_collection as get_chroma
from app.core.embeddings import embed_texts

router = APIRouter(prefix="/knowledge-base")


@router.post("/upload")
async def upload_to_kb(
    file: UploadFile = File(...),
    category_id: int = Form(...),
):
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
        raw_text = extract_text(str(save_path))
        chunks = chunk_text(raw_text)
        if not chunks:
            raise HTTPException(400, "No extractable content found in file")

        embeddings = embed_texts(chunks)
        doc_id = str(uuid.uuid4())
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"document_id": doc_id, "source": file.filename, "chunk_index": i} for i in range(len(chunks))]
        chroma = get_chroma()
        chroma.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

        article = db.create_article(
            title=Path(file.filename).stem,
            content=raw_text[:10000],
            status="published",
            category_id=category_id,
            author_name="مستورد",
        )
        return {"data": {**article, "chunks_count": len(chunks)}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")
    finally:
        os.remove(save_path)


@router.get("/tree")
def get_tree():
    return {"data": db.build_tree()}


@router.get("/categories")
def get_categories():
    return {"data": db.get_all_categories()}


@router.post("/categories")
def add_category(body: dict):
    name = body.get("name")
    if not name:
        raise HTTPException(400, "name is required")
    cat = db.create_category(
        name=name,
        parent_id=body.get("parent_id"),
        description=body.get("description", ""),
    )
    return {"data": cat}


@router.delete("/categories/{category_id}")
def remove_category(category_id: int):
    if not db.delete_category(category_id):
        raise HTTPException(404, "Category not found")
    return {"data": {"id": category_id}}


@router.get("/articles")
def get_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    search: str | None = None,
):
    articles, meta = db.list_articles(
        page=page, per_page=per_page,
        category_id=category_id, search=search,
    )
    return {"data": articles, "meta": meta}


@router.get("/articles/{article_id}")
def get_article(article_id: int):
    article = db.get_article(article_id)
    if not article:
        raise HTTPException(404, "Article not found")
    db.increment_views(article_id)
    article["total_views"] += 1
    return {"data": article}


@router.post("/articles")
def add_article(body: dict):
    title = body.get("title")
    if not title:
        raise HTTPException(400, "title is required")
    article = db.create_article(
        title=title,
        content=body.get("content", ""),
        status=body.get("status", "published"),
        category_id=body.get("category_id"),
        author_name=body.get("author_name", "المؤلف"),
    )
    return {"data": article}


@router.put("/articles/{article_id}")
def edit_article(article_id: int, body: dict):
    article = db.update_article(article_id, body)
    if not article:
        raise HTTPException(404, "Article not found")
    return {"data": article}


@router.delete("/articles/{article_id}")
def remove_article(article_id: int):
    if not db.delete_article(article_id):
        raise HTTPException(404, "Article not found")
    return {"data": {"id": article_id}}


@router.get("/articles/{article_id}/comments")
def get_comments(article_id: int):
    return {"data": db.get_comments(article_id)}


@router.post("/articles/{article_id}/comments")
def add_comment(article_id: int, body: dict):
    body_text = body.get("body")
    if not body_text:
        raise HTTPException(400, "body is required")
    if not db.get_article(article_id):
        raise HTTPException(404, "Article not found")
    comment = db.add_comment(
        article_id=article_id,
        body=body_text,
        user_name=body.get("user_name", "مستخدم"),
    )
    return {"data": comment}


@router.get("/articles/{article_id}/activity")
def get_activity(article_id: int):
    return {"data": db.get_activity(article_id)}


@router.get("/articles/{article_id}/tickets")
def get_tickets(article_id: int, page: int = Query(1, ge=1)):
    tickets, meta = db.get_tickets(article_id, page=page)
    return {"data": tickets, "meta": meta}


@router.post("/ingest")
def ingest_qa(body: dict):
    title = body.get("title")
    content = body.get("content")
    if not title or not content:
        raise HTTPException(400, "title and content are required")

    category_id = body.get("category_id")
    if not category_id:
        category_id = db.get_faq_category_id()

    article = db.create_article(
        title=title,
        content=content,
        status="published",
        category_id=category_id,
        author_name=body.get("author_name", "وكيل الدعم"),
    )

    try:
        from app.core.ingestion import chunk_text
        from app.core.embeddings import embed_texts

        full_text = f"{title}\n\n{content}"
        chunks = chunk_text(full_text)
        if chunks:
            embeddings = embed_texts(chunks)
            doc_id = str(uuid.uuid4())
            ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
            metadatas = [
                {"document_id": doc_id, "source": f"livechat:{article['id']}", "chunk_index": i}
                for i in range(len(chunks))
            ]
            chroma = get_chroma()
            chroma.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
            return {"data": {**article, "chunks_count": len(chunks)}}
    except Exception:
        pass

    return {"data": article}


@router.post("/articles/{article_id}/vote")
def vote(article_id: int, body: dict):
    helpful = body.get("helpful")
    if helpful is None:
        raise HTTPException(400, "helpful is required")
    article = db.vote_article(article_id, bool(helpful))
    if not article:
        raise HTTPException(404, "Article not found")
    return {"data": article}
