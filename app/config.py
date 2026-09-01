import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
UPLOADS_DIR = BASE_DIR / "uploads"

os.makedirs(CHROMA_DB_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
TOP_K = 8

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 2048

COLLECTION_NAME = "esamco_knowledge_base"

ALLOWED_EXTENSIONS = {".pdf"}
MAX_FILE_SIZE_MB = 50
MAX_QUERY_LENGTH = 500

LLM_ERROR_PREFIX = "عذراً، حدث خطأ في الاتصال"

# The prompt instructs the model to lead with this exact phrase when the
# context doesn't answer the question - far more reliable than guessing at
# however it might naturally phrase "I don't know" (which varies run to run).
NO_ANSWER_MARKER = "لا تتوفر معلومات كافية للإجابة على هذا السؤال"

HUMAN_REQUEST_KEYWORDS = {
    "خدمة العملاء", "موظف", "مندوب", "أتكلم مع شخص", "اتكلم مع حد",
    "انسان", "إنسان", "شخص حقيقي","خدمه عملاء",
    "human", "agent", "representative", "customer service", "talk to someone",
}

# Chroma always returns its top-K nearest vectors, even for a nonsense query
# with no genuinely relevant match - so "no answer" can't be detected from
# retrieval alone. These are phrases the model itself tends to use when the
# retrieved context doesn't actually answer the question.
NO_ANSWER_PATTERNS = {
    "لا يوجد معلومات", "لا توجد معلومات", "لا يوجد أي معلومات", "لا توجد أي معلومات",
    "لا يوجد إجابة", "لا توجد إجابة", "لا يوجد اجابة", "لا توجد اجابة",
    "لا يوجد إجابة متوفرة", "لا توجد إجابة متوفرة",
    "لا أملك معلومات", "ليس لدي معلومات", "لا تحتوي المعلومات على",
    "لم أجد إجابة", "لم أجد معلومات", "لا يمكنني الإجابة", "لا أستطيع الإجابة",
}
