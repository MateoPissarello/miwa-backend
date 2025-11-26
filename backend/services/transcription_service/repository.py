from __future__ import annotations

from typing import Dict, Iterable, Optional

import boto3
from botocore.exceptions import ClientError


class TranscriptionStatusRepository:
    """Lightweight repository around a DynamoDB table to track transcription status."""

    def __init__(self, table_name: str, region: str):
        if not table_name:
            raise ValueError("DynamoDB table name for transcriptions is required")
        self.table_name = table_name
        self.resource = boto3.resource("dynamodb", region_name=region)
        self.table = self.resource.Table(table_name)

    def get_status(self, recording_id: str) -> Optional[Dict]:
        try:
            response = self.table.get_item(Key={"recording_id": recording_id})
        except ClientError as exc:
            raise RuntimeError(f"Unable to read transcription status: {exc}") from exc
        return response.get("Item")

    def batch_get_statuses(self, recording_ids: Iterable[str]) -> Dict[str, Dict]:
        keys = [{"recording_id": rid} for rid in recording_ids]
        if not keys:
            return {}

        try:
            response = self.resource.batch_get_item(RequestItems={self.table_name: {"Keys": keys}})
        except ClientError as exc:
            raise RuntimeError(f"Unable to batch read transcription status: {exc}") from exc

        items = response.get("Responses", {}).get(self.table_name, [])
        return {item["recording_id"]: item for item in items}

    def upsert_status(self, item: Dict) -> None:
        try:
            self.table.put_item(Item=item)
        except ClientError as exc:
            raise RuntimeError(f"Unable to update transcription status: {exc}") from exc
