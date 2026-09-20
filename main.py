import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from google import genai

from ingest import chunk_documents, load_documents
from retrieval import embed_chunks
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
        documents = load_documents()

        app.state.documents = {
            document["source"]: document["text"]
            for document in documents
        }
        chunks = chunk_documents(documents)

        app.state.embedded_chunks = embed_chunks(client, chunks)
        app.state.client = client

        yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
