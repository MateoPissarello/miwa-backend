"""Dependency registration for the meetings service."""

from __future__ import annotations

import boto3
from botocore.config import Config

from kernel import Kernel
from kernel.runtime import get_kernel

from .repository import MeetingArtifactRepository


CAPABILITY_DDB_REPOSITORY = "capability.meetings.repository"
CAPABILITY_DDB_CLIENT = "capability.meetings.ddb_client"


def _create_dynamodb_client(kernel: Kernel):
    settings = kernel.settings
    return boto3.client(
        "dynamodb",
        region_name=settings.AWS_REGION,
        config=Config(retries={"max_attempts": 10, "mode": "adaptive"}, connect_timeout=5, read_timeout=10),
    )


def _create_repository(kernel: Kernel) -> MeetingArtifactRepository:
    client = kernel.resolve(CAPABILITY_DDB_CLIENT)
    return MeetingArtifactRepository(
        client=client,
        table_name=kernel.settings.DDB_TABLE_NAME,
    )


def register_dependencies(kernel: Kernel) -> None:
    """Register kernel capabilities consumed by the meetings service."""

    kernel.register_capability(CAPABILITY_DDB_CLIENT, _create_dynamodb_client)
    kernel.register_capability(CAPABILITY_DDB_REPOSITORY, _create_repository)


def get_repository() -> MeetingArtifactRepository:
    """FastAPI dependency resolving the configured repository."""

    kernel = get_kernel()
    return kernel.resolve(CAPABILITY_DDB_REPOSITORY)

