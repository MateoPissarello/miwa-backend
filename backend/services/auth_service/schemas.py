from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from pydantic import field_serializer
from pydantic import ConfigDict
from datetime import datetime


class User(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)
    email: EmailStr = Field(..., min_length=1, max_length=50)
    address: str = Field(..., min_length=1, max_length=200)
    birthdate: str = Field(..., description="User's birthdate")
    gender: str = Field(..., min_length=1, max_length=20)
    picture: str = Field(..., min_length=1)
    phone_number: str = Field(..., min_length=1, max_length=20)
    family_name: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=50)


class UserLogin(BaseModel):
    email: str
    password: str


class UserConfirmCognito(BaseModel):
    email: EmailStr
    code: str


class CreateUserBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    email: EmailStr = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=50)
    role: Optional[str] = Field("client", min_length=1, max_length=20)


class RetrieveUserBase(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    email: str
    role: str
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("last_login", when_used="json")
    def _serialize_last_login(self, v: datetime | None):
        return v.isoformat() if v else None


class RetrieveUserLogin:
    user_id: int
    email: EmailStr
    role: str

    model_config = {"from_attributes": True}


class UpdateUserBase(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr] = Field(None, min_length=1, max_length=50)
    role: Optional[str] = Field(None, min_length=1, max_length=20)
    password: Optional[str] = Field(None, min_length=8, max_length=50)


class MfaBeginReq(BaseModel):
    session: str
    email: EmailStr


class MfaVerifyReq(BaseModel):
    session: str
    email: EmailStr
    code: str
