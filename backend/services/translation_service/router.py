# -*- coding: utf-8 -*-
"""FastAPI router for video translation endpoints (S3 only - no database)."""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
)
from fastapi import status as response_status
from fastapi.responses import JSONResponse

# Schemas
from .schemas import (
    VideoFile,
    TranslationStatus,
    VideoTranslation,
    TranslationListResponse,
)

# Functions / services
from .functions import (
    list_video_files,
    get_translation_status,
    get_video_translation,
    upload_video_file,
    delete_video_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/translations", tags=["Video Translations"])


# ---------------------------
# Health
# ---------------------------
@router.get("/health")
async def translation_service_health():
    """Health check endpoint for translation service."""
    return {"status": "ok", "service": "translation_service"}


# ---------------------------
# Listado de videos (S3)
# ---------------------------
@router.get("/videos", response_model=TranslationListResponse)
async def list_videos():
    """List all video files in S3 with their translation status."""
    try:
        videos_data = list_video_files()
        videos = [
            VideoFile(
                file_key=v["file_key"],
                file_name=v["file_name"],
                size=v["size"],
                last_modified=v["last_modified"],
                has_translation=v["has_translation"],
            )
            for v in videos_data
        ]
        return TranslationListResponse(videos=videos, total=len(videos))
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        raise HTTPException(
            status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving video list: {str(e)}",
        )


@router.get("/videos/{video_key}/status", response_model=TranslationStatus)
async def get_video_status(video_key: str):
    """Get the translation status for a specific video in S3 processing."""
    try:
        status_data = get_translation_status(video_key)
        return TranslationStatus(
            video_key=status_data["video_key"],
            status=status_data["status"],
            progress=status_data.get("progress"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video status: {e}")
        raise HTTPException(
            status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving video status: {str(e)}",
        )


@router.get("/videos/{video_key}/translation", response_model=VideoTranslation)
async def get_video_translation_endpoint(video_key: str):
    """Get the translation result for a specific video from S3."""
    try:
        translation_data = get_video_translation(video_key)
        if not translation_data:
            raise HTTPException(
                status_code=response_status.HTTP_404_NOT_FOUND,
                detail=f"Translation not found for video: {video_key}",
            )
        return VideoTranslation(
            original_file=translation_data["original_file"],
            original_language=translation_data["original_language"],
            original_text=translation_data["original_text"],
            translations=translation_data["translations"],
            processed_at=translation_data["processed_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video translation: {e}")
        raise HTTPException(
            status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving translation: {str(e)}",
        )


@router.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file to S3 for processing."""
    try:
        if not file.content_type or not file.content_type.startswith("video/"):
            raise HTTPException(
                status_code=response_status.HTTP_400_BAD_REQUEST,
                detail="File must be a video",
            )

        file_content = await file.read()
        success = upload_video_file(file_content, file.filename)
        if not success:
            raise HTTPException(
                status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload video",
            )

        return JSONResponse(
            status_code=response_status.HTTP_201_CREATED,
            content={
                "message": "Video uploaded successfully",
                "filename": file.filename,
                "status": "uploaded - processing will begin automatically",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        raise HTTPException(
            status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading video: {str(e)}",
        )


@router.delete("/videos/{video_key}")
async def delete_video(video_key: str):
    """Delete a video file and its translation from S3."""
    try:
        success = delete_video_file(video_key)
        if not success:
            raise HTTPException(
                status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete video",
            )
        return JSONResponse(
            content={"message": "Video deleted successfully", "video_key": video_key}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        raise HTTPException(
            status_code=response_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting video: {str(e)}",
        )

