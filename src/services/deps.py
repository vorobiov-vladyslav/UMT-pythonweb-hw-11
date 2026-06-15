from fastapi import Depends
from sqlalchemy.orm import Session

from database.db import get_db
from repository.contacts import ContactRepository
from repository.users import UserRepository
from services.contacts import ContactService
from services.users import UserService


def get_contact_repository(db: Session = Depends(get_db)) -> ContactRepository:
    return ContactRepository(db)


def get_contact_service(
    repo: ContactRepository = Depends(get_contact_repository),
) -> ContactService:
    return ContactService(repo)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(repo)
