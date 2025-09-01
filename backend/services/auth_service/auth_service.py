from fastapi import HTTPException
from .schemas import User, UserLogin
from utils.cognito_repository import CognitoRepository


class AuthService:
    def __init__(self):
        self.repo = CognitoRepository()

    def register_user(self, user: User):
        try:
            user_data = user.model_dump()
            response = self.repo.sign_up_user(user_data)
            return {"message": "User registered successfully", "response": response}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def confirm_user(self, email: str, code: str):
        try:
            response = self.repo.confirm_user(email, code)
            return {"message": "User confirmed successfully", "response": response}
        except HTTPException as e:
            raise e

    def login_user(self, user_login: UserLogin):
        """
        Devuelve:
          - {"status":"OK","tokens":{...}}
          - {"status":"MFA_SETUP","session":"..."}
          - {"status":"SOFTWARE_TOKEN_MFA","session":"..."}
        """
        try:
            return self.repo.login_user(user_login.email, user_login.password)
        except Exception as e:
            # OJO: este mensaje se muestra en el front; no tapes errores de param mal formados
            raise HTTPException(
                status_code=400,
                detail=f"Incorrect email or password, msg: {e}",
            )

    def mfa_setup_begin(self, session: str, email: str):
        """
        Paso 1 (MFA_SETUP): obtener secreto/otpauth y posible nueva session.
        """
        try:
            return self.repo.mfa_setup_begin(session=session, email_for_label=email)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def mfa_setup_verify(self, session: str, email: str, code: str):
        """
        Paso 2 (MFA_SETUP): verificar código y completar challenge -> tokens.
        """
        try:
            return self.repo.mfa_setup_verify(session=session, email=email, code=code)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def mfa_challenge(self, session: str, email: str, code: str):
        """
        Usuario ya tiene TOTP; responde al challenge con el código -> tokens.
        """
        try:
            return self.repo.mfa_challenge_respond(session=session, email=email, code=code)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
