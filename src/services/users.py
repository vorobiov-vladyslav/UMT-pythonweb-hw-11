from __future__ import annotations

from libgravatar import Gravatar

from database.models import User
from repository.users import UserRepository
from services.exceptions import DuplicateUser


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    def register(self, username: str, email: str, hashed_password: str) -> User:
        if self.repo.get_by_email(email) is not None:
            raise DuplicateUser
        if self.repo.get_by_username(username) is not None:
            raise DuplicateUser
        avatar: str | None = None
        try:
            avatar = Gravatar(email).get_image()
        except Exception:  # gravatar is best-effort; never block registration
            avatar = None
        return self.repo.create(username, email, hashed_password, avatar)

    def get_by_email(self, email: str) -> User | None:
        return self.repo.get_by_email(email)

    def confirm(self, email: str) -> None:
        self.repo.confirmed_email(email)

    def update_avatar(self, email: str, url: str) -> User:
        return self.repo.update_avatar_url(email, url)

    def update_refresh_token(self, email: str, token: str | None) -> None:
        self.repo.update_refresh_token(email, token)
