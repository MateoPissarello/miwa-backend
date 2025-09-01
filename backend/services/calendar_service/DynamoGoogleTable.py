from core.config import settings
import boto3
from google.oauth2.credentials import Credentials


class DynamoGoogleTable:
    def __init__(self):
        self.table_name = settings.DYNAMO_GOOGLE_TOKENS_TABLE
        self.ddb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
        self.table = self.ddb.Table(self.table_name)

    def save_tokens(self, user_sub: str, creds: Credentials):
        self.table.put_item(
            Item={
                "user_sub": user_sub,
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
                "scope": " ".join(creds.scopes or []),
                "token_uri": creds.token_uri or "https://oauth2.googleapis.com/token",
                "client_id": settings.GOOGLE_CLIENT_ID,
                # client_secret lo tomamos de env, no por usuario
            }
        )

    def load_tokens(self, user_sub: str):
        r = self.table.get_item(Key={"user_sub": user_sub})
        return r.get("Item")
