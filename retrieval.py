import os

from google import genai
from google.genai import types

from ingest import chunk_documents, load_documents

EMBEDDING_MODEL = "gemini-embedding-2"

def embed_text(client, text):
    response = client.models.embed_content(
        model    = EMBEDDING_MODEL,
        contents = text,
        config   = types.EmbedContentConfig(output_dimensionality=768),  
    )

    embedding, = response.embeddings

    return embedding.values

def embed_chunks(client, chunks):
    embedded_chunks = []

    for chunk in chunks:
        vector = embed_text(
            client,
            f"title: {chunk['source']} | text: {chunk['text']}",
        )
        embedded_chunks.append({
            **chunk,
            "embedding": vector,
        })
        print(
            f"Embedded {len(embedded_chunks)}/{len(chunks)}: "
            f"{chunk['source']} chunk {chunk['chunk_index']} "
            f"({len(vector)} dimensions)"
        )

    return embedded_chunks

def cosine_similarity(a, b):
    if len(a) != len(b):
        raise ValueError("Vectors must have the same dimensions")

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = sum(x * x for x in a) ** 0.5
    magnitude_b = sum(y * y for y in b) ** 0.5

    if magnitude_a == 0 or magnitude_b == 0:
        raise ValueError("Vectors must have nonzero magnitude")

    return dot_product / (magnitude_a * magnitude_b)

def search(client, question, embedded_chunks, top_k=3):
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    question_vector = embed_text(
        client,
        f"task: search result | query: {question}",
    )

    results = []

    for chunk in embedded_chunks:
        score = cosine_similarity(question_vector, chunk["embedding"])
        results.append({
            "source": chunk["source"],
            "chunk_index": chunk["chunk_index"],
            "text": chunk["text"],
            "score": score,
        })

    results.sort(key=lambda result: result["score"], reverse=True)
    return results[:top_k]

if __name__ == "__main__":
    chunks = chunk_documents(load_documents())

    with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
        embedded_chunks = embed_chunks(client, chunks)

        print("\nReady. Enter a question, or type 'quit' to exit.")

        while True:
            question = input("\nQuestion: ").strip()

            if question.lower() == "quit":
                break

            if not question:
                continue

            results = search(client, question, embedded_chunks, top_k=3)

            print(f"\nQUERY:\n{question}")

            for rank, result in enumerate(results, start=1):
                print(f"\nRESULT {rank}")
                print(f"score: {result['score']:.4f}")
                print(f"source: {result['source']}")
                print(f"chunk: {result['chunk_index']}")
                print(f"text:\n{result['text']}")