# api/files.py
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import Response, FileResponse
import os
import shutil
from core.config import settings
from core.security import get_current_user
from database.manager import DatabaseManager

router = APIRouter(prefix="/files", tags=["files"])
db = DatabaseManager()

@router.post("/{chat_id}/upload")
async def upload_file(
    chat_id: int,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
        
    file_path = os.path.join(settings.UPLOAD_DIR, f"{chat_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename, "path": file_path}

@router.get("/export/{chat_id}")
async def export_chat(
    chat_id: int,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
        
    messages = db.get_chat_messages(chat_id)
    transcript = ""
    for msg in messages:
        transcript += f"{msg['role'].upper()}: {msg['content']}\n"

    return Response(
        content=transcript,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=chat_{chat_id}.txt"}
    )

@router.get("/{chat_id}/{filename}")
async def get_file(
    chat_id: int,
    filename: str,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
        
    file_path = os.path.join(settings.UPLOAD_DIR, f"{chat_id}_{filename}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
