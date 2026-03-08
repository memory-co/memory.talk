"""Ingest API endpoints."""
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from memory_talk.models import IngestRequest, Message
from memory_talk.storage import Storage

router = APIRouter()
storage = Storage()


@router.post("/api/ingest")
async def ingest_conversation(request: IngestRequest) -> JSONResponse:
    """Ingest conversation data.

    Args:
        request: Conversation data

    Returns:
        Success response
    """
    # Convert messages to Message objects if they are dicts
    messages = request.messages
    if messages and isinstance(messages[0], dict):
        messages = [Message(**msg) for msg in request.messages]

    storage.save_conversation(
        platform=request.platform,
        session_id=request.session_id,
        messages=messages,
        metadata=request.metadata,
    )

    return JSONResponse({"status": "ok", "session_id": request.session_id})


@router.post("/api/ingest/blob")
async def ingest_blob(
    platform: str = Form(...),
    file: UploadFile = File(...),
) -> JSONResponse:
    """Ingest a blob file.

    Args:
        platform: Platform name
        file: File to upload

    Returns:
        Success response with hash
    """
    file_data = await file.read()
    file_hash = storage.save_blob(platform, file_data, file.filename)

    return JSONResponse({"status": "ok", "hash": file_hash})
