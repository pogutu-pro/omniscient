from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    registration_number: str
    full_name: str
    email: str
    programme: str
    year_of_study: int
    preferences: dict


class StudentCreate(BaseModel):
    registration_number: str = Field(min_length=4, max_length=32)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    programme: str = Field(min_length=2, max_length=120)
    year_of_study: int = Field(ge=1, le=6)


class StudentLogin(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    student: StudentOut
