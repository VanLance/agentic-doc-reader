from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DOCS_DIR = PROJECT_ROOT / "docs"


def load_documents():
    documents = []

    for path in sorted(DOCS_DIR.glob("*.md")):
        documents.append({
            "source": path.relative_to(PROJECT_ROOT).as_posix(),
            "text": path.read_text(encoding="utf-8"),
        })

    return documents

def chunk_documents(documents, chunk_size=800, overlap=120):
    if not 0 <= overlap < chunk_size:
        raise ValueError("Require 0 <= overlap < chunk_size")

    chunks = []
    step = chunk_size - overlap

    for document in documents:
        text = document["text"]

        for chunk_index, start in enumerate(range(0, len(text), step)):
            end = min(start + chunk_size, len(text))

            chunks.append({
                "source": document["source"],
                "chunk_index": chunk_index,
                "text": text[start:end],
            })

            if end == len(text):
                break

    return chunks

if __name__ == "__main__":
    documents = load_documents()
    chunks = chunk_documents(documents)

    print(f"Loaded {len(documents)} documents; created {len(chunks)} chunks.")

    for chunk in chunks:
        print("\n" + "=" * 80)
        print(
            f"Source: {chunk['source']} | "
            f"Chunk: {chunk['chunk_index']} | "
            f"Characters: {len(chunk['text'])}"
        )
        print("-" * 80)
        print(chunk["text"])