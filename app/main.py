"""FinAssist ID — FastAPI entrypoint."""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import llm
from app.config import Settings, get_settings

app = FastAPI(title="FinAssist ID", version="0.1.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    model: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, settings: Settings = Depends(get_settings)) -> ChatResponse:
    try:
        answer = llm.chat(req.message, settings)
    except llm.LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(answer=answer, model=settings.ollama_model)
