import boto3
from botocore.exceptions import ClientError
from core.config import settings
import hmac
import hashlib
import base64
from time import time
from urllib.parse import quote


class CognitoRepository:
    def __init__(self):
        self.client = boto3.client("cognito-idp", region_name=settings.AWS_REGION)

    def _secret_hash(self, email: str) -> str:
        digest = hmac.new(
            settings.COGNITO_SECRET.encode("utf-8"),
            (email + settings.COGNITO_CLIENT_ID).encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode()

    def mfa_totp_begin(self, access_token: str):
        try:
            resp = self.client.associate_software_token(AccesToken=access_token)
            secret = resp["SecretCode"]
            issuer = "MIWA"
            label = f"{issuer}:{access_token[:10]}"
            otpauth = f"otpauth://totp/{quote(label)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
            return {"secret": secret, "otpauth": otpauth}
        except Exception as e:
            return {"error": str(e)}

    def confirm_user(self, email: str, code: str):
        try:
            response = self.client.confirm_sign_up(
                ClientId=settings.COGNITO_CLIENT_ID,
                SecretHash=self._secret_hash(email),
                Username=email,
                ConfirmationCode=code,
            )
            return {"message": "User confirmed successfully", "response": response}
        except ClientError as e:
            raise e

    def sign_up_user(self, user_data: dict):
        try:
            response = self.client.sign_up(
                ClientId=settings.COGNITO_CLIENT_ID,
                SecretHash=self._secret_hash(user_data["email"]),
                Username=user_data["email"],
                Password=user_data["password"],
                UserAttributes=[
                    {"Name": "updated_at", "Value": str(int(time()))},
                    {"Name": "nickname", "Value": user_data["nickname"]},
                    {"Name": "address", "Value": user_data["address"]},
                    {"Name": "birthdate", "Value": user_data["birthdate"]},
                    {"Name": "gender", "Value": user_data["gender"]},
                    {"Name": "picture", "Value": user_data["picture"]},
                    {"Name": "phone_number", "Value": user_data["phone_number"]},
                    {"Name": "family_name", "Value": user_data["family_name"]},
                    {"Name": "name", "Value": user_data["name"]},
                ],
            )
            return response
        except ClientError as e:
            raise e

    def login_user(self, email: str, password: str):
        try:
            response = self.client.initiate_auth(
                ClientId=settings.COGNITO_CLIENT_ID,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "EMAIL": email,
                    "PASSWORD": password,
                },
            )
            return response["AuthenticationResult"]["AccessToken"]
        except ClientError as e:
            raise e
