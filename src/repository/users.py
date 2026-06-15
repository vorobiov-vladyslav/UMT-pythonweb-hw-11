from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalars(select(User).where(User.email == email)).first()

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalars(select(User).where(User.username == username)).first()

    def create(
        self,
        username: str,
        email: str,
        hashed_password: str,
        avatar: str | None = None,
    ) -> User:
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            avatar=avatar,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def confirmed_email(self, email: str) -> None:
        user = self.get_by_email(email)
        user.confirmed = True
        self.db.commit()

    def update_avatar_url(self, email: str, url: str) -> User:
        user = self.get_by_email(email)
        user.avatar = url
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_refresh_token(self, email: str, token: str | None) -> None:
        user = self.get_by_email(email)
        user.refresh_token = token
        self.db.commit()
