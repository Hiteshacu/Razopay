from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class AuthorityCreate(BaseModel):
    authority_name: str = Field(..., min_length=2)
    department: str = Field(..., min_length=2)
    email: EmailStr


class AuthorityDto(BaseModel):
    authority_id: str
    authority_name: str
    department: str
    email: str
    created_at: str
    status: str


class KeyGenerateRequest(BaseModel):
    authority_id: str
    authority_name: str | None = None


class PublicKeyDto(BaseModel):
    key_id: str
    authority_id: str
    authority_name: str
    public_key_pem: str
    algorithm: str
    key_size: int
    created_at: str
    active: bool
    fingerprint_sha256: str
    storage_path_optional: str | None = None


class SignDocumentResponse(BaseModel):
    success: bool
    document_id: str
    signed_file_url: str
    download_url: str
    signed_file_storage_path: str
    signed_filename: str
    storage_type: str
    key_id: str
    authority_id: str
    message: str


class VerificationResponse(BaseModel):
    success: bool
    result: str
    reason: str
    authority_name: str | None = None
    authority_id: str | None = None
    key_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=1200)
    language: str = Field("en", pattern="^(en|kn|hi)$")


class ChatSource(BaseModel):
    title: str
    url: str
    content: str | None = None


class ChatResponse(BaseModel):
    success: bool
    answer: str
    language: str
    sources: list[ChatSource] = Field(default_factory=list)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str
    message: str
