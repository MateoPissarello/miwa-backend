from fastapi import APIRouter
from .auth_service import AuthService
from .schemas import User, UserLogin, UserConfirmCognito

router = APIRouter(prefix="/cognito/auth", tags=["Cognito"])

auth_service = AuthService()


@router.post("/signup")
def signup(user: User):
    return auth_service.register_user(user)


@router.post("/confirm")
def confirm(user_confirm: UserConfirmCognito):
    return auth_service.confirm_user(user_confirm.email, user_confirm.code)


@router.post("/login")
def login(user_login: UserLogin):
    return auth_service.login_user(user_login)
