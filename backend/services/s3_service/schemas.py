from typing import Optional

from pydantic import BaseModel, EmailStr


class PresignSignupReq(BaseModel):
    email: EmailStr
    filename: str
    content_type: Optional[str] = None


class PresignSignupResp(BaseModel):
    put_url: str
    get_url: str
    key: str


class UploadResponse(BaseModel):
    key: str
    url: str
