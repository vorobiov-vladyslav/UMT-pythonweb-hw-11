from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database.db import get_db
from schemas import RequestEmail, Token, TokenRefreshRequest, UserCreate, UserResponse
from services.auth import (
    Hash,
    create_access_token,
    create_refresh_token,
    get_email_from_token,
    verify_refresh_token,
)
from services.deps import get_user_service
from services.email import send_verification_email
from services.exceptions import DuplicateUser
from services.users import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    hashed_password = Hash().get_password_hash(payload.password)
    try:
        user = service.register(payload.username, payload.email, hashed_password)
    except DuplicateUser:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
    background_tasks.add_task(
        send_verification_email, user.email, user.username, str(request.base_url)
    )
    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: UserService = Depends(get_user_service),
) -> Token:
    # The OAuth2 form's `username` field carries the user's email.
    user = service.get_by_email(form_data.username)
    if user is None or not Hash().verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.confirmed:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not confirmed")
    access_token = create_access_token({"sub": user.email})
    refresh_token = create_refresh_token({"sub": user.email})
    service.update_refresh_token(user.email, refresh_token)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh_token", response_model=Token)
def refresh_token(
    body: TokenRefreshRequest,
    db: Session = Depends(get_db),
    service: UserService = Depends(get_user_service),
) -> Token:
    user = verify_refresh_token(body.refresh_token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    access_token = create_access_token({"sub": user.email})
    new_refresh_token = create_refresh_token({"sub": user.email})
    service.update_refresh_token(user.email, new_refresh_token)
    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.get("/confirmed_email/{token}")
def confirmed_email(token: str, service: UserService = Depends(get_user_service)) -> dict[str, str]:
    email = get_email_from_token(token)
    user = service.get_by_email(email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification error")
    if user.confirmed:
        return {"message": "Email already confirmed"}
    service.confirm(email)
    return {"message": "Email confirmed"}


@router.post("/request_email")
def request_email(
    body: RequestEmail,
    request: Request,
    background_tasks: BackgroundTasks,
    service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    user = service.get_by_email(body.email)
    if user is not None and not user.confirmed:
        background_tasks.add_task(
            send_verification_email, user.email, user.username, str(request.base_url)
        )
    return {"message": "Check your email for confirmation."}
