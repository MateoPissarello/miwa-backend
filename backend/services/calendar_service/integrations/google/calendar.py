# integrations/google/calendar.py
import logging

from googleapiclient.discovery import build
from starlette.concurrency import run_in_threadpool
from google.auth.transport.requests import Request as GRequest
from google.auth.exceptions import RefreshError

from ...integrations.google.tokens import build_creds
from ...DynamoGoogleTable import DynamoGoogleTable

dynamo_google_table = DynamoGoogleTable()
logger = logging.getLogger(__name__)


async def with_service(creds, fn):
    svc = build("calendar", "v3", credentials=creds)
    return await run_in_threadpool(fn, svc)


async def ensure_creds(user_sub: str):
    item = dynamo_google_table.load_tokens(user_sub)
    if not item:
        return None
    creds = build_creds(item)
    if not creds:
        return None

    if not creds.valid:
        if creds.refresh_token:
            try:
                creds.refresh(GRequest())
            except RefreshError as exc:
                logger.warning(
                    "No se pudo refrescar el token de Google Calendar para %s: %s",
                    user_sub,
                    exc,
                )
                dynamo_google_table.delete_tokens(user_sub)
                return None
            else:
                dynamo_google_table.save_tokens(user_sub, creds)  # persistir refresh
        else:
            return None
    return creds
