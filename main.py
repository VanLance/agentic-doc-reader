import os

from fastapi import FastAPI
from google import genai
from pydantic import BaseModel

app = FastAPI()

class AskRequest(BaseModel):
    question: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
def ask(request: AskRequest):
    with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
        response = client.interactions.create(
            model="gemini-3.8-flash",
            system_instruction=(
                "You are a developer documentation assistant. "
                "Answer concisely. You have not been given this project's "
                "documentation, so do not invent project-specific details."
            ),
            input=request.question,
            generation_config={
                "max_output_tokens":1024,
                "thinking_level":"low",
            }
        )

        print("Question: ", request.question)
        print("Response: ", response)

    return {"answer": response.output_text}

