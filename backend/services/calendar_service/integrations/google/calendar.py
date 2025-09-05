# integrations/google/calendar.py
from googleapiclient.discovery import build
from starlette.concurrency import run_in_threadpool
from google.auth.transport.requests import Request as GRequest
from ...integrations.google.tokens import build_creds
from ...DynamoGoogleTable import DynamoGoogleTable

dynamo_google_table = DynamoGoogleTable()


async def with_service(creds, fn):
    svc = build("calendar", "v3", credentials=creds)
    return await run_in_threadpool(fn, svc)


async def ensure_creds(user_sub: str):
    item = dynamo_google_table.load_tokens(user_sub)
    if not item:
        return None
    creds = build_creds(item)
    if creds and not creds.valid and creds.refresh_token:
        creds.refresh(GRequest())
        dynamo_google_table.save_tokens(user_sub, creds)  # persistir refresh
    return creds
