from pydantic import BaseModel
from pydantic import EmailStr
from typing import Literal


class TokenData(BaseModel):
    sub: str
    user_id: int
    email: EmailStr
    role: Literal["admin", "client"]
