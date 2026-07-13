from sentence_transformers import SentenceTransformer
from app.config import EMBEDDING_MODEL

_model = None


def get_embedding_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    return model.encode(text).tolist()
