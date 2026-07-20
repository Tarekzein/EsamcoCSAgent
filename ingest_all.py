from pathlib import Path
from app.core.ingestion import ingest_file, extract_text

for pdf in Path(".").glob("*.pdf"):

    if pdf.name.startswith("._"):
        continue

    print("=" * 60)
    print(pdf.name)

    text = extract_text(str(pdf))
    print("Characters:", len(text))

    result = ingest_file(str(pdf))
    print(result)