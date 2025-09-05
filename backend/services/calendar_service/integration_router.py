# routes/integrations_google.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode
from core.config import settings
from google_auth_oauthlib.flow import Flow
import hashlib
from utils.get_current_user_cognito import TokenData, get_current_user  # tu dependencia que expone user.sub
from .DynamoGoogleTable import DynamoGoogleTable
from .functions import create_state, verify_state

router = APIRouter(prefix="/integrations/google", tags=["Google Integrations"])

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_ID = settings.GOOGLE_CLIENT_ID
CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
REDIRECT_URI = settings.GOOGLE_REDIRECT_URI
STATE_SECRET = (settings.GOOGLE_STATE_SECRET or "").strip().strip('"').strip("'")


dynamo_google_table = DynamoGoogleTable()


@router.get("/auth-url")
def google_auth_url(current_user: TokenData = Depends(get_current_user)):
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": create_state(current_user.sub),  # puedes firmarlo si quieres
    }
    print("[auth-url] STATE_SECRET_SHA256:", hashlib.sha256(STATE_SECRET.encode()).hexdigest()[:16])
    return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


@router.get("/callback")
def google_callback(code: str, state: str):
    print("[callback] STATE_SECRET_SHA256:", hashlib.sha256(STATE_SECRET.encode()).hexdigest()[:16])
    try:
        payload = verify_state(state)
        user_sub = payload["sub"]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"state inválido: {e}")

    # 2) Intercambiar code por tokens
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    if not creds or not creds.token:
        raise HTTPException(400, "No se obtuvo token de Google")

    # 3) Guardar tokens ligados a ese user_sub
    dynamo_google_table.save_tokens(user_sub, creds)

    # 4) Redirigir al front (opcional)
    return RedirectResponse(settings.GOOGLE_AFTER_CONNECT, status_code=302)
