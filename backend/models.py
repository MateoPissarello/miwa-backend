from sqlalchemy import Column, Integer, String, Enum, DateTime
from datetime import datetime
import enum
from database import Base


class UserRole(enum.Enum):
    client = "client"
    admin = "admin"


class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, unique=True, nullable=False)
    last_name = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(Enum(UserRole, name="user_role"), default=UserRole.client)
    last_login = Column(DateTime, nullable=True, default=datetime.now)
