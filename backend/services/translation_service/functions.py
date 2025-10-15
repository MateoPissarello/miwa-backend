# -*- coding: utf-8 -*-
"""Functions for managing video translations (S3 only - no database)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# S3 Client
# ---------------------------------------------------------------------
try:
    s3_client = boto3.client("s3", region_name=settings.AWS_REGION)
except (ClientError, NoCredentialsError) as e:
    logger.warning(f"No se pudo inicializar el cliente de S3: {e}")
    s3_client = None


# ---------------------------------------------------------------------
# Helpers S3
# ---------------------------------------------------------------------
def get_bucket_name() -> str:
    """Obtiene el nombre del bucket a partir del ARN o nombre plano."""
    bucket_arn = settings.S3_BUCKET_ARN
    if bucket_arn.startswith("arn:aws:s3:::"):
        return bucket_arn.replace("arn:aws:s3:::", "")
    return bucket_arn


def list_video_files() -> List[dict]:
    """Lista archivos de video en el bucket S3 y marca si tienen traducción."""
    if not s3_client:
        return []

    try:
        bucket_name = get_bucket_name()
        video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"]

        response = s3_client.list_objects_v2(Bucket=bucket_name)
        videos: List[dict] = []

        for obj in response.get("Contents", []):
            key = obj["Key"]
            if any(key.lower().endswith(ext) for ext in video_extensions):
                has_translation = check_translation_exists(key)
                videos.append(
                    {
                        "file_key": key,
                        "file_name": key.split("/")[-1],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                        "has_translation": has_translation,
                    }
                )

        return videos
    except Exception as e:
        logger.error(f"Error listing video files: {e}")
        return []


def _translation_key_for_video(video_key: str) -> str:
    """Construye la clave en S3 para el JSON de traducciones de un video."""
    base_name = video_key.rsplit(".", 1)[0]
    return f"translations/{base_name}_translations.json"


def check_translation_exists(video_key: str) -> bool:
    """Verifica si existe el archivo de traducción en S3 para el video dado."""
    if not s3_client:
        return False
    try:
        bucket_name = get_bucket_name()
        translation_key = _translation_key_for_video(video_key)
        s3_client.head_object(Bucket=bucket_name, Key=translation_key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"404", "NotFound"}:
            return False
        logger.error(f"Error checking translation existence: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking translation existence: {e}")
        return False


def get_translation_status(video_key: str) -> dict:
    """Devuelve estado 'completed' si existe JSON de traducción, si no 'pending'."""
    has_translation = check_translation_exists(video_key)
    if has_translation:
        return {"video_key": video_key, "status": "completed", "progress": "100%"}
    return {"video_key": video_key, "status": "pending", "progress": None}


def get_video_translation(video_key: str) -> Optional[dict]:
    """Obtiene el contenido del JSON de traducción desde S3."""
    if not s3_client:
        return None
    try:
        bucket_name = get_bucket_name()
        translation_key = _translation_key_for_video(video_key)
        response = s3_client.get_object(Bucket=bucket_name, Key=translation_key)
        return json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            logger.info(f"Translation not found for video: {video_key}")
            return None
        logger.error(f"Error getting translation from S3: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting translation from S3: {e}")
        return None


def upload_video_file(file_content: bytes, file_name: str) -> bool:
    """Sube un archivo de video a S3."""
    if not s3_client:
        return False
    try:
        bucket_name = get_bucket_name()
        s3_client.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=file_content,
            Metadata={
                "uploaded-by": "miwa-backend",
                "upload-time": datetime.utcnow().isoformat()
            },
        )
        logger.info(f"Video uploaded successfully: {file_name}")
        return True
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        return False


def delete_video_file(video_key: str) -> bool:
    """Elimina el archivo de video y (si existe) su JSON de traducción en S3."""
    if not s3_client:
        return False
    try:
        bucket_name = get_bucket_name()
        # Eliminar video
        s3_client.delete_object(Bucket=bucket_name, Key=video_key)
        # Eliminar traducción (si existe)
        translation_key = _translation_key_for_video(video_key)
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=translation_key)
        except ClientError:
            pass
        logger.info(f"Video deleted successfully: {video_key}")
        return True
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        return False
