"""FinAssist ID — FastAPI entrypoint."""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import llm, rag, retrieval
from app.agent import SessionLimit, SessionStore
from app.config import Settings, get_settings
from app.security import client_identity, rate_limited_client, warn_if_open

app = FastAPI(title="FinAssist ID", version="0.4.0")
sessions = SessionStore()
warn_if_open(get_settings())


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
def chat(req: ChatRequest, settings: Settings = Depends(get_settings),
         client: str = Depends(rate_limited_client)) -> ChatResponse:
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


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(None, description="Omit to start a new session")


class ToolCallOut(BaseModel):
    seq: int
    turn: int
    tool: str
    arguments: dict
    status: str
    result: dict | None
    error_code: str | None
    at: str


class AgentResponse(BaseModel):
    session_id: str
    reply: str
    pending_order: dict | None
    tool_calls: list[ToolCallOut]
    guard: str | None = Field(None, description="Set when an output guard replaced the model's reply")


def _session(session_id: str, client: str):
    """404 for unknown sessions and for other clients' sessions alike (P4-04, MAN-01)."""
    try:
        return sessions.get(session_id, client)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found") from None


@app.post("/agent", response_model=AgentResponse)
def agent(req: AgentRequest, settings: Settings = Depends(get_settings),
          client: str = Depends(rate_limited_client)) -> AgentResponse:
    try:
        session = sessions.get_or_create(req.session_id, settings, client)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found") from None
    except SessionLimit:
        raise HTTPException(status_code=429, detail="Too many active sessions; try again later") from None
    except ValueError as exc:  # unknown AGENT_PROVIDER
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        out = session.handle(req.message)
    except llm.LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AgentResponse(**vars(out))


@app.get("/agent/{session_id}/log")
def agent_log(session_id: str, client: str = Depends(client_identity)) -> dict:
    """Every tool call of the session, in order: name, arguments, status, result, error code."""
    session = _session(session_id, client)
    return {"session_id": session_id, "tool_calls": [vars(e) for e in session.log]}


@app.get("/agent/{session_id}/state")
def agent_state(session_id: str, client: str = Depends(client_identity)) -> dict:
    """Mock broker state for assertions: portfolio, executed orders, pending order."""
    session = _session(session_id, client)
    return {"session_id": session_id, "portfolio": session.broker.get_portfolio(),
            "orders": session.broker.order_history(), "pending_order": session.pending}
