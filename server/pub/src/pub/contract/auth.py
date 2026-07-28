"""
Authentication API contracts
"""

from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator


class RegisterRequest(BaseModel):
    company_name: str
    contact_name: str
    phone: str
    email: str

    @field_validator("company_name", "contact_name", "phone")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("email is required")
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("email is required")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("invalid email format")
        return value


class RegisterResponse(BaseModel):
    tenant_id: UUID
    contact_id: UUID
    account_id: UUID
    account_username: str
    login_channel: str
    email_sent: bool

    model_config = ConfigDict(from_attributes=True)


class PasswordSetupRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("token is required")
        return normalized

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters")
        if value.startswith("!setup:"):
            raise ValueError("password uses a reserved prefix")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    account_id: UUID
    username: str
    tenant_id: UUID
    tenant_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    flag: int

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("current_password", "new_password")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized
