"""
Two kinds of bearer tokens:
- operator tokens, issued by the Lab (iss edugen-lab, aud edugen): accepted for study creation and progress
- participant tokens, issued here when a code is redeemed (iss edugen-review): scoped to one session and study
Every check of the course chapter 6.7 is applied: algorithm list, issuer, audience, expiry, required claims.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .db import utcnow

ALGORITHM = "HS256"
LAB_ISSUER, LAB_AUDIENCE = "edugen-lab", "edugen"
ISSUER, AUDIENCE = "edugen-review", "edugen-review"
_bearer = HTTPBearer(auto_error=False)
_REQUIRED = {"require": ["exp", "iat", "iss", "aud", "sub"]}


@dataclass(frozen=True)
class Caller:
    subject: str   # operator username, or participant ID
    role: str      # operator | expert | student
    study_id: Optional[str] = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def _token(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    if credentials is None:
        raise _unauthorized("A bearer token is required.")
    return credentials.credentials


def require_operator(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Caller:
    try:
        claims = jwt.decode(_token(credentials), config.LAB_JWT_SECRET, algorithms=[ALGORITHM], audience=LAB_AUDIENCE,
                            issuer=LAB_ISSUER, options=_REQUIRED)
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired operator token.") from None
    if claims.get("role") != "operator":
        raise HTTPException(403, "The operator role is required.")
    return Caller(claims["sub"], "operator")


def issue_participant_token(participant_id: str, role: str, study_id: str) -> str:
    now = utcnow()
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": participant_id, "role": role, "sid": study_id,
              "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=config.SESSION_TTL_HOURS)).timestamp())}
    return jwt.encode(claims, config.REVIEW_JWT_SECRET, algorithm=ALGORITHM)


def require_participant(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Caller:
    try:
        claims = jwt.decode(_token(credentials), config.REVIEW_JWT_SECRET, algorithms=[ALGORITHM], audience=AUDIENCE,
                            issuer=ISSUER, options=_REQUIRED)
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired session token.") from None
    return Caller(claims["sub"], claims.get("role", ""), claims.get("sid"))


def require_expert(caller: Caller = Depends(require_participant)) -> Caller:
    if caller.role != "expert":
        raise HTTPException(403, "This endpoint is for expert reviewers.")
    return caller


def require_student(caller: Caller = Depends(require_participant)) -> Caller:
    if caller.role != "student":
        raise HTTPException(403, "This endpoint is for students.")
    return caller
