"""FinAssist ID — FastAPI entrypoint."""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import llm, rag, retrieval
from app.config import Settings, get_settings

app = FastAPI(title="FinAssist ID", version="0.2.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class SourceOut(BaseModel):
    id: str
    title: str
    section: str
    url: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    refused: bool


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, settings: Settings = Depends(get_settings)) -> ChatResponse:
    try:
        result = rag.answer(req.message, settings)
    except retrieval.IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(
        answer=result.answer,
        refused=result.refused,
        sources=[SourceOut(**vars(s)) for s in result.sources],
    )
