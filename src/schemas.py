from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    phone: str = Field(min_length=1, max_length=20)
    birthday: date
    additional_data: str | None = Field(default=None, max_length=500)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(ContactBase):
    pass


class ContactRead(ContactBase):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# --- Users / auth ---


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    avatar: str | None
    confirmed: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class RequestEmail(BaseModel):
    email: EmailStr
