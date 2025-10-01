from fastapi import APIRouter
from fastapi import status as response_status
from fastapi import Body, Depends, HTTPException
from database import get_db
from utils.password_hasher import Hash
from sqlalchemy.orm import Session
from utils.login_logic import base_login
from services.auth_service.schemas import UpdateUserBase, UserLogin
from services.auth_service.schemas import CreateUserBase, RetrieveUserBase
from models import User
from services.auth_service.functions import create_user
from utils.RoleChecker import RoleChecker
from utils.get_current_user_cognito import TokenData, get_current_user
from .functions import update_last_login, get_all_users, update_user_data
from typing import List
import requests
import os

router = APIRouter(prefix="/auth", tags=["Authentication"])
admin_only = RoleChecker(allowed_roles=["admin"])

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "https://example.com/lambda-endpoint")
hash = Hash()


@router.post("/login", response_model=RetrieveUserBase, status_code=response_status.HTTP_200_OK)
async def login(data: UserLogin = Body(...), db: Session = Depends(get_db)) -> RetrieveUserBase:
    try:
        user_data = base_login(db, data)
    except HTTPException as e:
        if e.status_code == response_status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=response_status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        elif e.status_code == response_status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(
                status_code=response_status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
    usr_obj = update_last_login(user_data, db)
    return RetrieveUserBase.model_validate(usr_obj)


@router.post("/admin/login", response_model=RetrieveUserBase, status_code=response_status.HTTP_200_OK)
async def admin_login(data: UserLogin = Body(...), db: Session = Depends(get_db)) -> RetrieveUserBase:
    try:
        user = base_login(db, data)
    except HTTPException as e:
        if e.status_code == response_status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=response_status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        elif e.status_code == response_status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(
                status_code=response_status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
    if user.role.value not in ["admin"]:
        raise HTTPException(
            status_code=response_status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this resource",
        )
    user_data = update_last_login(user, db)
    return RetrieveUserBase.model_validate(user_data)


@router.post("/signup", response_model=RetrieveUserBase, status_code=response_status.HTTP_201_CREATED)
async def signup_user(user: CreateUserBase = Body(...), db: Session = Depends(get_db)) -> RetrieveUserBase:
    user_data = User(**user.model_dump(exclude_unset=True))
    user_data.password = hash.get_password_hash(user.password)

    try:
        if db.query(User).filter(User.email == user_data.email).first():
            raise HTTPException(status_code=response_status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        user_data = create_user(user_data, db)

        try:
            payload = {
                "email": user_data.email,
                "name": f"{user_data.first_name} {user_data.last_name}"
            }
            resp = requests.post(API_GATEWAY_URL, json=payload)
            if resp.status_code != 200:
                print(f"Error Lambda: {resp.text}")
        except Exception as e:
            print(f"No se pudo invocar Lambda: {e}")

        return user_data

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/delete/{user_id}", status_code=response_status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    """
    Delete a user by ID.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=response_status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()
    return {"detail": "User deleted successfully"}


@router.get("/users", response_model=List[RetrieveUserBase])
async def get_users(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
    admin: bool = Depends(admin_only),
):
    users = get_all_users(db)
    return users


@router.put("/update/{user_id}", response_model=RetrieveUserBase, status_code=response_status.HTTP_200_OK)
async def update_user(
    user_id: int,
    user_data: UpdateUserBase = Body(...),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Update a user by ID.
    """
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=response_status.HTTP_404_NOT_FOUND, detail="User not found")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    if user_data.password:
        user_data.password = hash.get_password_hash(user_data.password)
    if user_data.email != user.email:
        if db.query(User).filter(User.email == user_data.email).first():
            raise HTTPException(status_code=response_status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    new_user_data = update_user_data(user, user_data, db)
    return new_user_data
