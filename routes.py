from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent import AgentError, answer_question

router = APIRouter()


class AskRequest(BaseModel):
    question: str


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/ask")
def ask(request: AskRequest, http_request: Request):
    state = http_request.app.state
    try:
        answer = answer_question(
            request.question,
            state.client,
            state.embedded_chunks,
            state.documents,
        )
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"answer": answer}
