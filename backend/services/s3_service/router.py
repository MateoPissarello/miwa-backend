from fastapi import APIRouter, File, HTTPException, UploadFile, Query, Depends
from typing import List
from fastapi.responses import StreamingResponse
from typing import Optional
from fastapi.concurrency import run_in_threadpool
from utils.RoleChecker import RoleChecker
from utils.get_current_user_cognito import TokenData, get_current_user
from .functions import S3Storage
from .schemas import PresignSignupReq
import uuid
import mimetypes
from .deps import get_s3_storage

router = APIRouter(prefix="/s3", tags=["s3"])

all_users = RoleChecker(["client", "admin"])


@router.post("/upload", response_model=str)
async def upload_endpoint(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    folder: Optional[str] = Query(default="uploads"),
):
    s3: S3Storage = get_s3_storage()
    try:
        email = current_user.username
        if email is None:
            raise HTTPException(status_code=401, detail="Email claim missing in token")
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
        email = current_user.username
        if email is None:
            raise HTTPException(status_code=401, detail="Email claim missing in token")
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


# ============================================================================
# RECORDINGS ENDPOINTS (Video Translation System)
# ============================================================================

@router.get("/recordings/{email}")
async def list_recordings(
    email: str,
    current_user: TokenData = Depends(get_current_user),
):
    """List all video recordings for a user with transcription/summary status."""
    # Security: Only allow users to access their own recordings
    if current_user.username != email:
        raise HTTPException(status_code=403, detail="Access denied: You can only view your own recordings")
    
    s3: S3Storage = get_s3_storage()
    try:
        # List videos in uploads/{email}/
        video_prefix = f"uploads/{email}/"
        all_keys = await run_in_threadpool(lambda: s3.list_keys(prefix=video_prefix, max_items=1000))
        
        # Filter only video files (not in subdirectories)
        video_extensions = {'.mp4', '.mp3', '.wav', '.avi', '.mov', '.mkv'}
        recordings = []
        
        for key in all_keys:
            # Skip files in subdirectories (transcripciones/, resumenes/)
            relative_path = key.replace(video_prefix, '')
            if '/' in relative_path:
                continue
            
            # Check if it's a video file
            ext = '.' + key.split('.')[-1].lower() if '.' in key else ''
            if ext not in video_extensions:
                continue
            
            filename = relative_path
            base_name = filename.rsplit('.', 1)[0]
            
            # Check for transcription
            transcription_prefix = f"uploads/{email}/transcripciones/{base_name}_"
            transcription_keys = await run_in_threadpool(
                lambda: s3.list_keys(prefix=transcription_prefix, max_items=10)
            )
            has_transcription = len(transcription_keys) > 0
            
            # Check for summary
            summary_prefix = f"uploads/{email}/resumenes/{base_name}_"
            summary_keys = await run_in_threadpool(
                lambda: s3.list_keys(prefix=summary_prefix, max_items=10)
            )
            has_summary = len(summary_keys) > 0
            
            # Get file metadata
            try:
                metadata = await run_in_threadpool(lambda: s3.get_object_metadata(key))
                size = metadata.get('ContentLength', 0)
                uploaded_at = metadata.get('LastModified', '').isoformat() if metadata.get('LastModified') else None
            except:
                size = 0
                uploaded_at = None
            
            recordings.append({
                'filename': filename,
                'size': size,
                'uploaded_at': uploaded_at,
                'has_transcription': has_transcription,
                'has_summary': has_summary,
                'transcription_file': transcription_keys[0] if transcription_keys else None,
                'summary_file': summary_keys[0] if summary_keys else None,
            })
        
        return {
            'email': email,
            'recordings': recordings
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recordings/{email}/{filename}/transcription")
async def get_transcription(
    email: str,
    filename: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get transcription and translations for a video."""
    # Security: Only allow users to access their own recordings
    if current_user.username != email:
        raise HTTPException(status_code=403, detail="Access denied: You can only view your own transcriptions")
    
    s3: S3Storage = get_s3_storage()
    try:
        # Find the latest transcription file for this video
        base_name = filename.rsplit('.', 1)[0]
        transcription_prefix = f"uploads/{email}/transcripciones/{base_name}_"
        
        transcription_keys = await run_in_threadpool(
            lambda: s3.list_keys(prefix=transcription_prefix, max_items=100)
        )
        
        if not transcription_keys:
            raise HTTPException(
                status_code=404, 
                detail="Transcription not found. The video may still be processing."
            )
        
        # Get the most recent transcription
        latest_key = sorted(transcription_keys)[-1]
        
        # Download and parse JSON
        import json
        transcription_bytes = await run_in_threadpool(lambda: s3.download_as_bytes(latest_key))
        transcription_data = json.loads(transcription_bytes.decode('utf-8'))
        
        return transcription_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recordings/{email}/{filename}/summary")
async def get_summary(
    email: str,
    filename: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get AI-generated summary for a video."""
    # Security: Only allow users to access their own recordings
    if current_user.username != email:
        raise HTTPException(status_code=403, detail="Access denied: You can only view your own summaries")
    
    s3: S3Storage = get_s3_storage()
    try:
        # Find the latest summary file for this video
        base_name = filename.rsplit('.', 1)[0]
        summary_prefix = f"uploads/{email}/resumenes/{base_name}_"
        
        summary_keys = await run_in_threadpool(
            lambda: s3.list_keys(prefix=summary_prefix, max_items=100)
        )
        
        if not summary_keys:
            raise HTTPException(
                status_code=404, 
                detail="Summary not found. The video may still be processing."
            )
        
        # Get the most recent summary
        latest_key = sorted(summary_keys)[-1]
        
        # Download and parse JSON
        import json
        summary_bytes = await run_in_threadpool(lambda: s3.download_as_bytes(latest_key))
        summary_data = json.loads(summary_bytes.decode('utf-8'))
        
        return summary_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recordings/upload-url")
async def get_upload_url(
    email: str = Query(...),
    filename: str = Query(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Generate presigned URL for uploading a video directly to S3."""
    # Security: Only allow users to upload to their own folder
    if current_user.username != email:
        raise HTTPException(status_code=403, detail="Access denied: You can only upload to your own folder")
    
    s3: S3Storage = get_s3_storage()
    try:
        # Validate file extension
        video_extensions = {'.mp4', '.mp3', '.wav', '.avi', '.mov', '.mkv'}
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        if ext not in video_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed: {', '.join(video_extensions)}"
            )
        
        # Generate S3 key
        key = f"uploads/{email}/{filename}"
        
        # Determine content type
        content_type_map = {
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska',
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')
        
        # Generate presigned PUT URL (15 minutes expiration)
        upload_url = await run_in_threadpool(
            lambda: s3.presign_put_url(key, content_type=content_type, expires_seconds=900)
        )
        
        return {
            'upload_url': upload_url,
            'expires_in': 900,
            'upload_path': key
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
