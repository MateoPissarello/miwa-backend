from google.oauth2.credentials import Credentials
from core.config import settings


def build_creds(item) -> Credentials | None:
    if not item:
        return None
    return Credentials(
        token=item.get("access_token"),
        refresh_token=item.get("refresh_token"),
        token_uri=item.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=(item.get("scope") or "https://www.googleapis.com/auth/calendar").split(),
    )
