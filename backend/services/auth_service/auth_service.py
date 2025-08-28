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
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def login_user(self, user_login: UserLogin):
        try:
            token = self.repo.login_user(user_login.email, user_login.password)
            return {"access_token": token}
        except Exception as e:
            raise HTTPException(status_code=400, detail="Incorrect email or password, msg: " + str(e))
