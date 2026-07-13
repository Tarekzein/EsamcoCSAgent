import time
import httpx
from app.config import (
    COLLECTION_NAME, CHROMA_DB_DIR, TOP_K,
    OLLAMA_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    LLM_ERROR_PREFIX, HUMAN_REQUEST_KEYWORDS, NO_ANSWER_PATTERNS, NO_ANSWER_MARKER,
)
from app.core.embeddings import embed_query
import chromadb

_collection = None
_llm_client = None


def get_chroma_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(str(CHROMA_DB_DIR))
        _collection = client.get_or_create_collection(COLLECTION_NAME)
    return _collection


def get_llm_client():
    global _llm_client
    if _llm_client is None:
        _llm_client = httpx.Client(timeout=300)
    return _llm_client


GREETINGS = {"اهلا", "مرحبا", "hello", "hi", "hey", "سلام", "السلام عليكم", "تحية"}


def is_greeting(query: str) -> bool:
    q = query.strip().lower().rstrip("?!.،")
    return q in GREETINGS


def contains_human_request_keyword(query: str) -> bool:
    q = query.strip().lower()
    return any(keyword in q for keyword in HUMAN_REQUEST_KEYWORDS)


def is_no_answer(answer: str) -> bool:
    return NO_ANSWER_MARKER in answer or any(pattern in answer for pattern in NO_ANSWER_PATTERNS)


def call_llm(prompt: str) -> str:
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "temperature": LLM_TEMPERATURE,
        "options": {"num_predict": LLM_MAX_TOKENS},
    }
    try:
        client = get_llm_client()
        resp = client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        return f"{LLM_ERROR_PREFIX}: {str(e)}"


def build_prompt(query: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(context_chunks)
    return (
        "أنت مساعد شركة Esamco للتوظيف بالخارج.\n"
        "أجب على السؤال بناءً على المعلومات أدناه فقط.\n"
        f"إذا لم تحتوِ المعلومات على إجابة واضحة وحقيقية للسؤال، اكتب فقط "
        f'الجملة التالية بالضبط ولا شيء غيرها: "{NO_ANSWER_MARKER}"\n'
        "لا تخترع معلومات غير موجودة في النص أعلاه.\n"
        "كن ودوداً وتفاعلياً عند الإجابة. أجب بالعربية بتنسيق Markdown.\n\n"
        f"المعلومات:\n{context}\n\n"
        f"السؤال: {query}\n\n"
        "الإجابة:"
    )


def build_no_context_prompt(query: str) -> str:
    return (
        "أنت مساعد شركة Esamco للتوظيف بالخارج.\n"
        "المستخدم يسأل سؤالاً. إذا كان السؤال واضحاً أجب عليه من معرفتك العامة.\n"
        "إذا لم تفهم السؤال، اطلب توضيحاً بطريقة ودية.\n"
        "كن ودوداً وتفاعلياً. أجب بالعربية بتنسيق Markdown.\n\n"
        f"السؤال: {query}\n\n"
        "الإجابة:"
    )


def answer_query(query: str) -> dict:
    start = time.time()

    if is_greeting(query):
        greetings = {
            "اهلا": "أهلاً بك! كيف يمكنني مساعدتك اليوم؟",
            "مرحبا": "مرحباً! كيف أستطيع مساعدتك؟",
            "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته! كيف يمكنني مساعدتك؟",
            "hello": "Hello! How can I help you today?",
            "hi": "Hi there! How can I assist you?",
        }
        answer = greetings.get(query.strip().lower().rstrip("?!.،"), "أهلاً بك! كيف يمكنني مساعدتك؟")
        elapsed = int((time.time() - start) * 1000)
        return {"answer": answer, "sources": [], "latency_ms": elapsed, "needs_human": False}

    keyword_escalation = contains_human_request_keyword(query)

    query_vector = embed_query(query)
    collection = get_chroma_collection()

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=TOP_K,
    )

    if not results or not results["documents"] or not results["documents"][0]:
        prompt = build_no_context_prompt(query)
        answer = call_llm(prompt)
        elapsed = int((time.time() - start) * 1000)
        # No retrieved context at all is itself a low-confidence signal, so this
        # path always escalates regardless of keywords/LLM outcome.
        return {"answer": answer, "sources": [], "latency_ms": elapsed, "needs_human": True}

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    prompt = build_prompt(query, documents)
    answer = call_llm(prompt)

    sources = []
    raw_dists = [
        distances[i] if isinstance(distances[i], (int, float)) else distances[i][0]
        for i in range(len(documents))
    ]
    min_d = min(raw_dists)
    max_d = max(raw_dists)
    for i in range(len(documents)):
        score = round(1 - (raw_dists[i] - min_d) / (max_d - min_d + 1e-8), 4) if max_d != min_d else 1.0
        sources.append({
            "content": documents[i],
            "score": score,
            "document": metadatas[i].get("source", "unknown"),
        })

    # Escalate on an explicit request, the model itself saying it couldn't
    # answer from the context, or an outright failure - not on merely weak
    # retrieval scores, which would fire on almost every query.
    needs_human = (
        keyword_escalation
        or is_no_answer(answer)
        or answer.startswith(LLM_ERROR_PREFIX)
    )

    elapsed = int((time.time() - start) * 1000)
    return {"answer": answer, "sources": sources, "latency_ms": elapsed, "needs_human": needs_human}
