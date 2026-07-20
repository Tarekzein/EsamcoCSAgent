from groq import Groq
from app.config import GROQ_API_KEY, LLM_MODEL

client = Groq(api_key=GROQ_API_KEY)

def call_groq(prompt: str) -> str:
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.3,
        max_tokens=2048
    )

    return response.choices[0].message.content