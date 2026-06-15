from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile

from conf.config import settings
from conf.limiter import limiter
from database.models import User
from schemas import UserResponse
from services.auth import get_current_user
from services.deps import get_user_service
from services.upload_file import UploadFileService
from services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    description="No more than 10 requests per minute",
)
@limiter.limit("10/minute")
def me(request: Request, user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/avatar", response_model=UserResponse)
def update_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> User:
    avatar_url = UploadFileService(
        settings.cloudinary_name,
        settings.cloudinary_api_key,
        settings.cloudinary_api_secret,
    ).upload_file(file, user.username)
    return service.update_avatar(user.email, avatar_url)
