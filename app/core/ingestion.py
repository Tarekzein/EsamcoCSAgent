import uuid
from pathlib import Path

import fitz
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import chromadb
from app.config import (
    CHROMA_DB_DIR, COLLECTION_NAME,
    CHUNK_SIZE, CHUNK_OVERLAP, ALLOWED_EXTENSIONS,
)
from app.core.embeddings import embed_texts


_collection = None


def get_chroma_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(str(CHROMA_DB_DIR))
        _collection = client.get_or_create_collection(COLLECTION_NAME)
    return _collection


def extract_text(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    if ext == ".pdf":
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return text

    if ext in (".docx", ".doc"):
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)


def chunk_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
    )
    return splitter.split_text(text)


def ingest_file(file_path: str) -> dict:
    filename = Path(file_path).name
    raw_text = extract_text(file_path)
    chunks = chunk_text(raw_text)

    if not chunks:
        return {"document_id": None, "chunks_count": 0, "status": "empty_document"}

    embeddings = embed_texts(chunks)

    doc_id = str(uuid.uuid4())
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"document_id": doc_id, "source": filename, "chunk_index": i} for i in range(len(chunks))]

    collection = get_chroma_collection()
    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    return {"document_id": doc_id, "chunks_count": len(chunks), "status": "ok"}
