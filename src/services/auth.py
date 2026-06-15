from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from conf.config import settings
from database.db import get_db
from database.models import User
from repository.users import UserRepository

TokenType = Literal["access", "refresh"]


class Hash:
    password_hash = PasswordHash.recommended()  # argon2id

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.password_hash.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return self.password_hash.hash(password)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def create_token(data: dict, expires_delta: timedelta, token_type: TokenType) -> str:
    to_encode = data.copy()
    now = datetime.now(UTC)
    # `jti` makes every token unique even when iat/exp collide at second
    # resolution, so refresh-token rotation always yields a distinct string.
    to_encode.update(
        {
            "iat": now,
            "exp": now + expires_delta,
            "token_type": token_type,
            "jti": uuid4().hex,
        }
    )
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    delta = expires_delta or timedelta(seconds=settings.jwt_access_expiration_seconds)
    return create_token(data, delta, "access")


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    delta = expires_delta or timedelta(seconds=settings.jwt_refresh_expiration_seconds)
    return create_token(data, delta, "refresh")


def create_email_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.now(UTC)
    to_encode.update({"iat": now, "exp": now + timedelta(days=7)})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_email_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(
            status_code=422,
            detail="Invalid token for email verification",
        )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email = payload.get("sub")
        token_type = payload.get("token_type")
        if email is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = UserRepository(db).get_by_email(email)
    if user is None:
        raise credentials_exception
    return user


def verify_refresh_token(refresh_token: str, db: Session) -> User | None:
    try:
        payload = jwt.decode(
            refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        email = payload.get("sub")
        token_type = payload.get("token_type")
        if email is None or token_type != "refresh":
            return None
    except JWTError:
        return None

    user = UserRepository(db).get_by_email(email)
    if user is None or user.refresh_token != refresh_token:
        return None
    return user
