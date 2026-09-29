from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class Role(str, Enum):
    LEARNER = "LEARNER"  # the only role: every user learns from syllabi they upload themselves


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
