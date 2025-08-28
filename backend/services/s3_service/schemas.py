from pydantic import BaseModel, EmailStr
from typing import Optional


class PresignSignupReq(BaseModel):
    email: EmailStr
    filename: str
    content_type: Optional[str] = None


class PresignSignupResp(BaseModel):
    put_url: str
    get_url: str
    key: str
