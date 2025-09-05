from fastapi import APIRouter
from .auth_service import AuthService
from .schemas import User, UserLogin, UserConfirmCognito, MfaBeginReq, MfaVerifyReq

router = APIRouter(prefix="/cognito/auth", tags=["Cognito Auth"])

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


@router.post("/mfa/setup/begin")
def mfa_setup_begin(req: MfaBeginReq):
    return auth_service.mfa_setup_begin(session=req.session, email=req.email)


@router.post("/mfa/setup/verify")
def mfa_setup_verify(req: MfaVerifyReq):
    return auth_service.mfa_setup_verify(session=req.session, email=req.email, code=req.code)


@router.post("/mfa/challenge")
def mfa_challenge(req: MfaVerifyReq):
    return auth_service.mfa_challenge(session=req.session, email=req.email, code=req.code)
