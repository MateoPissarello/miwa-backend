"""DynamoDB repository for meeting artefacts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from boto3.dynamodb.conditions import Attr

from .schemas import MeetingArtifact, MeetingArtifactStatus, MeetingIdentifier


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utcnow() -> str:
    return datetime.utcnow().strftime(ISO_FORMAT)


class MeetingArtifactRepository:
    """Persist and query meeting artefacts in DynamoDB."""

    def __init__(self, client, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pk(self, identifier: MeetingIdentifier) -> str:
        return identifier.compose_pk()

    def _get_table(self):  # pragma: no cover - thin wrapper
        import boto3

        kwargs = {"region_name": self._client.meta.region_name}
        endpoint_url = getattr(self._client.meta, "endpoint_url", None)
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        resource = boto3.resource("dynamodb", **kwargs)
        return resource.Table(self._table_name)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def upsert_recording(
        self,
        identifier: MeetingIdentifier,
        *,
        ext: str,
        s3_key_recording: str,
        status: MeetingArtifactStatus,
    ) -> MeetingArtifact:
        now = _utcnow()
        table = self._get_table()
        table.update_item(
            Key={"pk": self._pk(identifier)},
            UpdateExpression=(
                "SET user_email=:email, meeting_name=:name, meeting_date=:date, "
                "basename=:basename, ext=:ext, s3_key_recording=:recording, "
                "status=:status, updated_at=:updated, "
                "created_at=if_not_exists(created_at, :created)"
            ),
            ExpressionAttributeValues={
                ":email": identifier.user_email,
                ":name": identifier.meeting_name,
                ":date": identifier.meeting_date,
                ":basename": identifier.basename,
                ":ext": ext,
                ":recording": s3_key_recording,
                ":status": status.value,
                ":updated": now,
                ":created": now,
            },
        )
        item = self.get(identifier)
        if item is None:  # pragma: no cover - defensive, Dynamo should return item
            raise RuntimeError("Failed to retrieve meeting artefact after upsert")
        return item

    def update_with_transcription(
        self,
        identifier: MeetingIdentifier,
        *,
        s3_key_transcription: str,
        status: MeetingArtifactStatus,
        duration_sec: Optional[float] = None,
        language: Optional[str] = None,
    ) -> MeetingArtifact:
        table = self._get_table()
        now = _utcnow()
        update = (
            "SET s3_key_transcription=:transcription, status=:status, updated_at=:updated"
        )
        values: Dict[str, Any] = {
            ":transcription": s3_key_transcription,
            ":status": status.value,
            ":updated": now,
        }
        if duration_sec is not None:
            update += ", duration_sec=:duration"
            values[":duration"] = Decimal(str(duration_sec))
        if language is not None:
            update += ", language=:language"
            values[":language"] = language
        table.update_item(Key={"pk": self._pk(identifier)}, UpdateExpression=update, ExpressionAttributeValues=values)
        item = self.get(identifier)
        if item is None:  # pragma: no cover
            raise RuntimeError("Meeting artefact missing after transcription update")
        return item

    def update_with_summary(
        self,
        identifier: MeetingIdentifier,
        *,
        s3_key_summary: str,
        status: MeetingArtifactStatus,
    ) -> MeetingArtifact:
        table = self._get_table()
        now = _utcnow()
        table.update_item(
            Key={"pk": self._pk(identifier)},
            UpdateExpression=(
                "SET s3_key_summary=:summary, status=:status, updated_at=:updated"
            ),
            ExpressionAttributeValues={
                ":summary": s3_key_summary,
                ":status": status.value,
                ":updated": now,
            },
        )
        item = self.get(identifier)
        if item is None:  # pragma: no cover
            raise RuntimeError("Meeting artefact missing after summary update")
        return item

    def update_status(
        self,
        identifier: MeetingIdentifier,
        *,
        status: MeetingArtifactStatus,
    ) -> MeetingArtifact:
        table = self._get_table()
        now = _utcnow()
        table.update_item(
            Key={"pk": self._pk(identifier)},
            UpdateExpression="SET status=:status, updated_at=:updated",
            ExpressionAttributeValues={
                ":status": status.value,
                ":updated": now,
            },
        )
        item = self.get(identifier)
        if item is None:  # pragma: no cover
            raise RuntimeError("Meeting artefact missing after status update")
        return item

    def mark_failed(
        self,
        identifier: MeetingIdentifier,
        *,
        status: MeetingArtifactStatus = MeetingArtifactStatus.FAILED,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> MeetingArtifact:
        table = self._get_table()
        now = _utcnow()
        update = "SET status=:status, updated_at=:updated"
        values: Dict[str, Any] = {
            ":status": status.value,
            ":updated": now,
        }
        if error_code is not None:
            update += ", error_code=:error_code"
            values[":error_code"] = error_code
        if error_message is not None:
            update += ", error_message=:error_message"
            values[":error_message"] = error_message
        table.update_item(Key={"pk": self._pk(identifier)}, UpdateExpression=update, ExpressionAttributeValues=values)
        item = self.get(identifier)
        if item is None:  # pragma: no cover
            raise RuntimeError("Meeting artefact missing after failure update")
        return item

    def get(self, identifier: MeetingIdentifier) -> Optional[MeetingArtifact]:
        table = self._get_table()
        response = table.get_item(Key={"pk": self._pk(identifier)})
        item = response.get("Item")
        if not item:
            return None
        return MeetingArtifact.from_ddb(item)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_meetings(
        self,
        *,
        user_email: Optional[str] = None,
        meeting_name: Optional[str] = None,
        status: Optional[MeetingArtifactStatus] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MeetingArtifact], int]:
        table = self._get_table()
        filter_expression = None
        if user_email:
            filter_expression = Attr("user_email").eq(user_email)
        if meeting_name:
            expr = Attr("meeting_name").eq(meeting_name)
            filter_expression = expr if filter_expression is None else filter_expression & expr
        if status:
            expr = Attr("status").eq(status.value)
            filter_expression = expr if filter_expression is None else filter_expression & expr
        if from_date:
            expr = Attr("meeting_date").gte(from_date)
            filter_expression = expr if filter_expression is None else filter_expression & expr
        if to_date:
            expr = Attr("meeting_date").lte(to_date)
            filter_expression = expr if filter_expression is None else filter_expression & expr

        scan_kwargs: Dict[str, Any] = {}
        if filter_expression is not None:
            scan_kwargs["FilterExpression"] = filter_expression

        items: List[Dict[str, Any]] = []
        start_key = None
        while True:
            if start_key is not None:
                scan_kwargs["ExclusiveStartKey"] = start_key
            response = table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break

        items.sort(key=lambda item: (item.get("meeting_date", ""), item.get("basename", "")), reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]
        return [MeetingArtifact.from_ddb(i) for i in page_items], total

    # ------------------------------------------------------------------
    # Utilities for tests/debugging
    # ------------------------------------------------------------------
    def batch_write(self, artefacts: Iterable[MeetingArtifact]) -> None:  # pragma: no cover - helper
        table = self._get_table()
        with table.batch_writer() as batch:
            for artefact in artefacts:
                batch.put_item(Item=artefact.to_ddb_item())

