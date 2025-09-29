from fastapi import APIRouter, File, HTTPException, UploadFile, Query, Depends
from typing import List
from fastapi.responses import StreamingResponse
from typing import Optional
from fastapi.concurrency import run_in_threadpool
from utils.RoleChecker import RoleChecker
from utils.get_current_user_cognito import get_current_user
from .functions import S3Storage
from sqlalchemy.orm import Session
from database import get_db
from utils.schemas import TokenData
from .schemas import PresignSignupReq
import uuid
import mimetypes
from .deps import get_s3_storage

router = APIRouter(prefix="/s3", tags=["s3"])

all_users = RoleChecker(["user", "admin"])


@router.post("/upload", response_model=str)
async def upload_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
    folder: Optional[str] = Query(default="uploads"),
):
    s3: S3Storage = get_s3_storage()
    try:
        email = current_user.email
        # Upload and return a presigned GET URL (private-by-default)
        url = await run_in_threadpool(
            lambda: s3.upload_fileobj(
                file.file,
                key=f"{folder}/{email}/{file.filename}",
                content_type=file.content_type or "application/octet-stream",
            )
        )
        return url
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[str])
async def list_endpoint(
    max_items: Optional[int] = Query(default=None, ge=1, le=10000),
    current_user: TokenData = Depends(get_current_user),
    folder: Optional[str] = Query(default="uploads"),
):
    s3: S3Storage = get_s3_storage()
    try:
        email = current_user.email
        prefix = f"{folder}/{email}/"
        keys = await run_in_threadpool(lambda: s3.list_keys(prefix=prefix, max_items=max_items))
        return keys
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presign-setup")
def presign_for_signup(req: PresignSignupReq):
    try:
        if not req.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Content type must be an image")

        s3: S3Storage = get_s3_storage()
        if req.filename and "." in req.filename:
            ext = req.filename.rsplit(".", 1)[-1].lower()
        elif req.content_type:
            ext_guess = mimetypes.guess_extension(req.content_type) or ""
            ext = ext_guess
        key = f"avatars/pending/{req.email}/{uuid.uuid4().hex}.{ext}"

        put_url = s3.presign_put_url(
            key=key,
            content_type=req.content_type or "application/octet-stream",
            expires_seconds=900,
        )
        get_url = s3.presign_get_url(key=key, expires_seconds=3600)
        return {"put_url": put_url, "get_url": get_url, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# (A) Stream the object bytes back to the client (simple; loads into memory)
@router.get("/download/{key:path}")
async def download_stream(key: str):
    if ".." in key:
        raise HTTPException(status_code=400, detail="Invalid key")
    s3: S3Storage = get_s3_storage()
    try:
        data: bytes = await run_in_threadpool(lambda: s3.download_as_bytes(key))

        # Try to guess a reasonable content type from the key
        import mimetypes

        media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"

        return StreamingResponse(
            content=iter([data]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{key.split("/")[-1]}"'},
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Object not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# (B) Or: return a short‑lived presigned URL (best for large files/CDN browser downloads)
@router.get("/download-url/{key:path}", response_model=str)
async def download_url(key: str, expires_seconds: int = Query(900, ge=60, le=604800)):
    if ".." in key:
        raise HTTPException(status_code=400, detail="Invalid key")
    s3: S3Storage = get_s3_storage()
    try:
        url = await run_in_threadpool(lambda: s3.presign_get_url(key, expires_seconds=expires_seconds))
        return url
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
