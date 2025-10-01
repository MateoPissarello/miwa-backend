from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import User
from utils.get_current_user_cognito import TokenData, get_current_user


class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = set(allowed_roles)

    def __call__(
        self,
        current_user: TokenData = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if current_user.email is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user email claim is required",
            )

        user = db.query(User).filter(User.email == current_user.email).first()
        if user is None or user.role.value not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
