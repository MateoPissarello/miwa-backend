from sqlalchemy.orm import Session
from models import User
from datetime import datetime

from services.auth_service.schemas import UpdateUserBase


def create_user(user: User, db: Session) -> User:
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_last_login(user: User, db: Session) -> User:
    user.last_login = datetime.now()
    db.commit()
    db.refresh(user)
    return user


def get_all_users(db: Session):
    return db.query(User).all()


def update_user_data(user: User, data: UpdateUserBase, db: Session) -> User:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user
