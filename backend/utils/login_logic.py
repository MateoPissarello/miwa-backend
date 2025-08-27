from fastapi import HTTPException
from fastapi import status as response_status
from utils.password_hasher import Hash
from sqlalchemy.orm import Session
from models import User
from services.auth_service.schemas import UserLogin


def base_login(db: Session, data: UserLogin):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=response_status.HTTP_404_NOT_FOUND, detail="User not found")
    hash = Hash()
    if not hash.verify_password(data.password, user.password):
        raise HTTPException(status_code=response_status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return user


