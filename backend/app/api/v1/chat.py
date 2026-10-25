"""AI assistant chat endpoint — grounded help for the analyst (uses AI provider)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.session import get_session

router = APIRouter()


class ChatTurn(BaseModel):
    role: str          # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    message: str
    history: list[ChatTurn] = []


@router.post("")
def chat(
    body: ChatIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Tool-calling assistant: may run an action (analyze/stats/navigate) or just answer.

    Returns {reply, action?} where action = {type:"navigate", view, target?} for the UI.
    """
    from app.services.agent import run

    out = run(session, body.message, [(t.role, t.content) for t in body.history])
    return {"reply": out.get("reply", ""), "action": out.get("action")}
