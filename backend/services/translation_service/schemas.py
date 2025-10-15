# -*- coding: utf-8 -*-
"""Pydantic schemas for video translation service."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------
# S3: listado de videos y estado
# ---------------------------------------------------------------------
class VideoFile(BaseModel):
    """Información de un archivo de video en S3."""
    file_key: str
    file_name: str
    size: int
    last_modified: datetime
    has_translation: bool


class TranslationStatus(BaseModel):
    """Estado de traducción para un video."""
    video_key: str
    status: str  # "pending", "processing", "completed", "failed"
    progress: Optional[str] = None


class VideoTranslation(BaseModel):
    """
    Resultado de traducción (flujo S3). 
    Nota: `processed_at` puede venir como str (ISO) o datetime.
    """
    original_file: str
    original_language: str
    original_text: str
    translations: Dict[str, str]
    processed_at: Optional[str] = None  # o Optional[datetime]


class TranslationListResponse(BaseModel):
    """Respuesta para listar videos en S3 con estado."""
    videos: List[VideoFile]
    total: int


# ---------------------------------------------------------------------
# DB: CRUD de traducciones
# ---------------------------------------------------------------------
class VideoTranslationRequest(BaseModel):
    """Request para crear/actualizar una traducción (DB)."""
    video_key: str = Field(..., description="Clave del video en S3")
    original_text: str = Field(..., description="Texto original extraído del video")
    translations: Dict[str, str] = Field(..., description="Traducciones por idioma")
    source_language: Optional[str] = None


class CreateTranslationRequest(BaseModel):
    """Request para crear manualmente una traducción (DB)."""
    video_key: str
    source_language: Optional[str] = None
    original_text: Optional[str] = None
    translations: Optional[Dict[str, str]] = None


class VideoTranslationResponse(BaseModel):
    """Respuesta de una traducción almacenada en DB."""
    id: int
    video_key: str
    source_language: Optional[str] = None
    original_text: Optional[str] = None
    translations: Optional[Dict[str, str]] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VideoTranslationListResponse(BaseModel):
    """Lista paginada de traducciones (DB)."""
    translations: List[VideoTranslationResponse]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------
class TranslationWebhookPayload(BaseModel):
    """Payload recibido desde Lambda webhook."""
    video_key: str
    original_text: str
    translations: Dict[str, str]
    source_language: Optional[str] = None
    # timestamp del webhook si lo necesitas:
    # timestamp: Optional[str] = None
