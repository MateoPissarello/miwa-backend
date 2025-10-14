# deps/cognito_auth.py
import time
from functools import lru_cache
from typing import Any, Dict, Optional

import boto3
import requests
from botocore.exceptions import ClientError
from core.config import settings
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwk, jwt
from jose.utils import base64url_decode
from pydantic import BaseModel


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")  # solo para FastAPI flow; no usado por Cognito


class TokenData(BaseModel):
    sub: str
    username: Optional[str] = None  # "cognito:username"
    email: Optional[str] = None
    scope: Optional[str] = None  # "aws.cognito.signin.user.admin" o tus custom scopes
    token_use: str  # "access" o "id"
    exp: int
    user_id: Optional[int] = None
    role: Optional[str] = None


@lru_cache(maxsize=1)
def _get_jwks() -> Dict[str, Any]:
    resp = requests.get(settings.COGNITO_JWKS_URL, timeout=5)
    resp.raise_for_status()
    return resp.json()


@lru_cache(maxsize=1)
def _get_cognito_client():
    return boto3.client("cognito-idp", region_name=settings.AWS_REGION)


def _find_key(kid: str) -> Optional[Dict[str, str]]:
    jwks = _get_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    # si no encontramos, refrescamos el cache y reintenta una vez
    _get_jwks.cache_clear()
    jwks = _get_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    return None


def _verify_signature_and_get_claims(token: str) -> Dict[str, Any]:
    # 1) localizar la clave por 'kid'
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Missing kid header")

    key_dict = _find_key(kid)
    if not key_dict:
        raise HTTPException(status_code=401, detail="Key not found in JWKS")

    # 2) verificar firma a bajo nivel (RS256)
    public_key = jwk.construct(key_dict)
    message, encoded_sig = token.rsplit(".", 1)
    decoded_sig = base64url_decode(encoded_sig.encode())
    if not public_key.verify(message.encode(), decoded_sig):
        raise HTTPException(status_code=401, detail="Invalid token signature")

    # 3) leer claims sin verificar (la firma ya la validamos arriba)
    claims = jwt.get_unverified_claims(token)
    return claims


def _validate_claims(claims: Dict[str, Any], expected_use: str = "access") -> TokenData:
    now = int(time.time())

    # exp
    if claims.get("exp") is None or now >= int(claims["exp"]):
        raise HTTPException(status_code=401, detail="Token expired")

    # iss
    if claims.get("iss") != settings.COGNITO_ISSUER:
        raise HTTPException(status_code=401, detail="Invalid issuer")

    # aud/client_id (Cognito usa 'aud' en ID tokens y 'client_id' en access tokens)
    aud_ok = (claims.get("aud") == settings.COGNITO_CLIENT_ID) or (
        claims.get("client_id") == settings.COGNITO_CLIENT_ID
    )
    if not aud_ok:
        raise HTTPException(status_code=401, detail="Invalid audience")

    # token_use
    if claims.get("token_use") != expected_use:
        raise HTTPException(status_code=401, detail="Invalid token use")

    # mapear a tu modelo
    return TokenData(
        sub=claims.get("sub"),
        username=claims.get("cognito:username"),
        email=claims.get("email"),
        scope=claims.get("scope"),
        token_use=claims["token_use"],
        exp=int(claims["exp"]),
    )


def _enrich_from_cognito(data: TokenData, access_token: str) -> TokenData:
    needs_email = data.email is None
    username_is_sub = data.username in (None, data.sub)

    if not needs_email and not username_is_sub:
        return data

    client = _get_cognito_client()
    try:
        response = client.get_user(AccessToken=access_token)
    except ClientError as exc:
        error_code = exc.response["Error"].get("Code")
        if error_code in {"NotAuthorizedException", "InvalidParameterException"}:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        raise HTTPException(status_code=500, detail="Unable to retrieve user information from Cognito")

    attributes = {item["Name"]: item["Value"] for item in response.get("UserAttributes", [])}
    email = attributes.get("email")
    username = email or response.get("Username")

    return data.copy(update={
        "email": email if needs_email else data.email,
        "username": username if username_is_sub else data.username,
    })


async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    try:
        claims = _verify_signature_and_get_claims(token)
        data = _validate_claims(claims, expected_use="access")  # tu API debe recibir ACCESS TOKENS
        return _enrich_from_cognito(data, token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
