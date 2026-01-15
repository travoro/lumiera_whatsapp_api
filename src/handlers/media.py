"""Temporary media file hosting for Twilio."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
import time
from typing import Dict
from src.utils.logger import log

router = APIRouter()

# In-memory storage for temporary files (path -> expiry_time)
temp_files: Dict[str, float] = {}
TEMP_FILE_EXPIRY = 300  # 5 minutes


def cleanup_expired_files():
    """Remove expired temporary files."""
    current_time = time.time()
    expired_files = [
        path for path, expiry in temp_files.items()
        if current_time > expiry
    ]
    
    for file_path in expired_files:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                log.info(f"🗑️ Cleaned up expired temp file: {file_path}")
        except Exception as e:
            log.warning(f"⚠️ Could not clean up expired file {file_path}: {e}")
        
        del temp_files[file_path]


def register_temp_file(file_path: str) -> str:
    """Register a temporary file for serving.
    
    Args:
        file_path: Path to the temporary file
        
    Returns:
        URL path to access the file
    """
    # Cleanup expired files first
    cleanup_expired_files()
    
    # Generate a unique ID from the file path
    file_id = os.path.basename(file_path)
    
    # Register the file with expiry time
    expiry_time = time.time() + TEMP_FILE_EXPIRY
    temp_files[file_path] = expiry_time
    
    log.info(f"📝 Registered temp file: {file_id} (expires in {TEMP_FILE_EXPIRY}s)")
    
    return f"/media/temp/{file_id}"


@router.get("/media/temp/{file_id}")
async def serve_temp_file(file_id: str):
    """Serve a temporary file.
    
    This endpoint allows Twilio to download files that we've temporarily
    downloaded from external sources (like PlanRadar).
    """
    log.info(f"📥 Request to serve temp file: {file_id}")
    
    # Cleanup expired files
    cleanup_expired_files()
    
    # Find the file path
    file_path = None
    for path in temp_files.keys():
        if os.path.basename(path) == file_id:
            file_path = path
            break
    
    if not file_path or not os.path.exists(file_path):
        log.warning(f"⚠️ Temp file not found: {file_id}")
        raise HTTPException(status_code=404, detail="File not found or expired")
    
    # Check if expired
    if time.time() > temp_files[file_path]:
        log.warning(f"⚠️ Temp file expired: {file_id}")
        try:
            os.unlink(file_path)
            del temp_files[file_path]
        except:
            pass
        raise HTTPException(status_code=404, detail="File expired")
    
    log.info(f"✅ Serving temp file: {file_id}")

    # Determine media type from extension
    media_type = "application/octet-stream"
    if file_path.endswith('.pdf'):
        media_type = "application/pdf"
    elif file_path.endswith('.png'):
        media_type = "image/png"
    elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
        media_type = "image/jpeg"

    # Strip extension from display filename for cleaner look
    # The media_type header tells clients it's a PDF, so extension is optional
    display_filename = file_id
    if file_id.endswith('.pdf'):
        display_filename = file_id[:-4]  # Remove .pdf extension
    elif file_id.endswith('.png'):
        display_filename = file_id[:-4]  # Remove .png extension
    elif file_id.endswith('.jpg'):
        display_filename = file_id[:-4]  # Remove .jpg extension
    elif file_id.endswith('.jpeg'):
        display_filename = file_id[:-5]  # Remove .jpeg extension

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=display_filename
    )
