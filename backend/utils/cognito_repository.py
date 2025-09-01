import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
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

    def _otpauth_url(self, label: str, secret: str, issuer: str = "MIWA") -> str:
        return f"otpauth://totp/{quote(label)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"

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
            err = e.response["Error"]["Code"]
            if err in ("CodeMismatchException",):
                raise HTTPException(400, "Código inválido.")
            if err in ("ExpiredCodeException",):
                raise HTTPException(400, "El código expiró. Reenvía un nuevo código.")
            if err in ("UserNotFoundException",):
                raise HTTPException(404, "Usuario no encontrado.")
            if err in ("NotAuthorizedException",):  # ya confirmado u otro estado
                raise HTTPException(409, "El usuario ya está confirmado.")
            raise HTTPException(500, f"Error confirmando usuario: {err}")

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
                    "USERNAME": email,
                    "PASSWORD": password,
                    "SECRET_HASH": self._secret_hash(email),
                },
            )

            if "AuthenticationResult" in response:
                return {
                    "status": "OK",
                    "tokens": response["AuthenticationResult"],
                }

            if "ChallengeName" in response:
                return {
                    "status": response["ChallengeName"],
                    "session": response.get("Session"),
                    "params": response.get("ChallengeParameters", {}),
                }

            raise RuntimeError("Unexpected response from Cognito")
        except ClientError as e:
            raise e

    def mfa_setup_begin(self, session: str, email_for_label: str):
        """
        Paso 1 (MFA_SETUP): obtener el secreto TOTP para mostrar QR.
        Usa Session (no AccessToken) porque estamos en flujo de challenge tras InitiateAuth.
        """
        try:
            resp = self.client.associate_software_token(Session=session)
            secret = resp["SecretCode"]
            # A veces devuelve una nueva Session; si no, reutiliza la recibida
            new_session = resp.get("Session", session)
            label = f"MIWA:{email_for_label}"
            return {
                "secret": secret,
                "otpauth": self._otpauth_url(label=label, secret=secret, issuer="MIWA"),
                "session": new_session,
            }
        except ClientError as e:
            raise e

    def mfa_setup_verify(self, session: str, email: str, code: str):
        """
        Paso 2 (MFA_SETUP): verificar el código de 6 dígitos y completar el challenge.
        Devuelve tokens si todo va bien.
        """
        try:
            # Verifica el TOTP con la Session del challenge
            resp = self.client.verify_software_token(Session=session, UserCode=code)
            if "Status" not in resp or resp["Status"] != "SUCCESS":
                raise RuntimeError("MFA setup verification failed")
            next_session = resp.get("Session", session)
            # Completa el challenge MFA_SETUP
            resp = self.client.respond_to_auth_challenge(
                ClientId=settings.COGNITO_CLIENT_ID,
                ChallengeName="MFA_SETUP",
                Session=next_session,
                ChallengeResponses={
                    "USERNAME": email,
                    "SECRET_HASH": self._secret_hash(email),
                    # No hace falta enviar el código aquí; ya se validó con verify_software_token
                },
            )

            if "AuthenticationResult" not in resp:
                raise RuntimeError("MFA setup did not return tokens")

            tokens = resp["AuthenticationResult"]

            # (Opcional) Dejar TOTP como preferido
            try:
                self.client.set_user_mfa_preference(
                    AccessToken=tokens["AccessToken"],
                    SoftwareTokenMfaSettings={"Enabled": True, "PreferredMfa": True},
                )
            except ClientError:
                # no bloquees el login si falla esta preferencia
                pass

            return {"status": "OK", "tokens": tokens}
        except ClientError as e:
            raise e

    def mfa_challenge_respond(self, session: str, email: str, code: str):
        """
        Usuario ya tenía TOTP. Responde al challenge SOFTWARE_TOKEN_MFA con el código y obtiene tokens.
        """
        try:
            resp = self.client.respond_to_auth_challenge(
                ClientId=settings.COGNITO_CLIENT_ID,
                ChallengeName="SOFTWARE_TOKEN_MFA",
                Session=session,
                ChallengeResponses={
                    "USERNAME": email,
                    "SOFTWARE_TOKEN_MFA_CODE": code,
                    "SECRET_HASH": self._secret_hash(email),
                },
            )

            if "AuthenticationResult" not in resp:
                raise RuntimeError("MFA challenge did not return tokens")

            return {"status": "OK", "tokens": resp["AuthenticationResult"]}
        except ClientError as e:
            raise e

    def mfa_totp_begin_logged(self, access_token: str, email_for_label: str):
        """
        Si ya tienes un AccessToken (usuario logueado) y quieres activar TOTP desde perfil.
        """
        try:
            resp = self.client.associate_software_token(AccessToken=access_token)
            secret = resp["SecretCode"]
            label = f"MIWA:{email_for_label}"
            return {
                "secret": secret,
                "otpauth": self._otpauth_url(label=label, secret=secret, issuer="MIWA"),
            }
        except ClientError as e:
            raise e
