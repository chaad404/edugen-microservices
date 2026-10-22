from fastapi import APIRouter, Depends, HTTPException

from .. import config
from ..schemas import LoginRequest, StreamTicketRequest
from ..security import Operator, credentials_valid, issue_stream_ticket, issue_token, require_operator

router = APIRouter(tags=["auth"])


@router.post("/auth/login", summary="Operator login; returns a bearer token")
def login(body: LoginRequest):
    if not credentials_valid(body.username, body.password):
        raise HTTPException(401, "Wrong username or password.")
    return {"access_token": issue_token(body.username), "token_type": "bearer",
            "expires_in": config.TOKEN_TTL_MINUTES * 60, "username": body.username, "role": "operator"}


@router.post("/auth/stream-tickets", summary="Short-lived ticket for one Server-Sent Events channel")
def stream_ticket(body: StreamTicketRequest, operator: Operator = Depends(require_operator)):
    return {"ticket": issue_stream_ticket(operator.username, body.channel), "channel": body.channel,
            "expires_in": config.STREAM_TICKET_TTL_SECONDS}
