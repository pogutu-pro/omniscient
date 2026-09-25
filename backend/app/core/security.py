"""Password hashing and JWT session tokens.

Kept deliberately small: this is the authentication *foundation* the brief
asks for (enough to identify a student and protect write endpoints), not a
full identity provider. It never trusts anything the LLM says about who a
user is — authorization checks always go through here.
"""
from __future__ import annotations

import datetime as dt

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, *, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=expire_minutes)
    payload = {"sub": subject, "exp": expire, "iat": dt.datetime.now(dt.timezone.utc)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Return the subject (student id) encoded in the token, or None if invalid."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
