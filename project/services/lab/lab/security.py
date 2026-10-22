"""
Operator authentication with signed JWTs (HS256). Every check of the course chapter 6.7 is applied:
fixed algorithm list, issuer, audience, expiry and required claims. Stream tickets are short-lived JWTs
for one SSE channel, because the browser's EventSource cannot send an Authorization header.
"""
import hmac
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .db import utcnow

ISSUER = "edugen-lab"
AUDIENCE = "edugen"                   # accepted by the Lab and by the Review service's operator endpoints
STREAM_AUDIENCE = "edugen-lab-stream"
ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Operator:
    username: str
    token: str


def credentials_valid(username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username.encode(), config.OPERATOR_USERNAME.encode())
    password_ok = hmac.compare_digest(password.encode(), config.OPERATOR_PASSWORD.encode())
    return user_ok and password_ok


def issue_token(username: str, *, audience: str = AUDIENCE, ttl: Optional[timedelta] = None,
                extra: Optional[dict] = None) -> str:
    now = utcnow()
    ttl = ttl or timedelta(minutes=config.TOKEN_TTL_MINUTES)
    claims = {"iss": ISSUER, "aud": audience, "sub": username, "role": "operator",
              "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp()), **(extra or {})}
    return jwt.encode(claims, config.JWT_SECRET, algorithm=ALGORITHM)


def decode(token: str, audience: str) -> dict:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM], audience=audience, issuer=ISSUER,
                          options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"}) from None


def require_operator(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Operator:
    if credentials is None:
        raise HTTPException(401, "A bearer token is required.", headers={"WWW-Authenticate": "Bearer"})
    claims = decode(credentials.credentials, AUDIENCE)
    if claims.get("role") != "operator":
        raise HTTPException(403, "The operator role is required.")
    return Operator(claims["sub"], credentials.credentials)


def issue_stream_ticket(username: str, channel: str) -> str:
    return issue_token(username, audience=STREAM_AUDIENCE, ttl=timedelta(seconds=config.STREAM_TICKET_TTL_SECONDS),
                       extra={"channel": channel})


def verify_stream_ticket(ticket: str, channel: str) -> dict:
    claims = decode(ticket, STREAM_AUDIENCE)
    if claims.get("channel") != channel:
        raise HTTPException(403, "The ticket was issued for a different channel.")
    return claims
