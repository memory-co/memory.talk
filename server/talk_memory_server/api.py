"""API routes for talk-memory server."""
import hashlib
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from talk_memory_server.models import (
    ConversationSummary,
    IngestRequest,
    Message,
    SearchResult,
)
from talk_memory_server.storage import Storage


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


@router.get("/api/conversations")
async def list_conversations(platform: Optional[str] = None) -> list[dict]:
    """List all conversations.

    Args:
        platform: Optional platform filter

    Returns:
        List of conversation summaries
    """
    conversations = storage.list_conversations(platform)
    return [conv.model_dump(mode="json") for conv in conversations]


@router.get("/api/conversations/{platform}/{session_id}")
async def get_conversation(
    platform: str,
    session_id: str,
) -> dict:
    """Get a specific conversation.

    Args:
        platform: Platform name
        session_id: Session ID

    Returns:
        Conversation data
    """
    result = storage.get_conversation(platform, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    metadata, messages = result
    return {
        "metadata": metadata.model_dump(mode="json"),
        "messages": [msg.model_dump(mode="json") for msg in messages],
    }


@router.get("/api/search")
async def search_conversations(q: str) -> list[dict]:
    """Search conversations.

    Args:
        q: Search query

    Returns:
        List of search results
    """
    results = storage.search(q)
    return [result.model_dump(mode="json") for result in results]
