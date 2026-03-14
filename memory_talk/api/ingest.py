"""Ingest API endpoints."""
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from memory_talk.models import IngestRequest, Message
from memory_talk.storage import Storage

router = APIRouter()
storage = Storage()


def match_subject_id(message: Message) -> str | None:
    """Match a subject ID based on message role and metadata.

    Matching rules:
    - role="user" → subject_id = "human-default"
    - role="assistant" + model in metadata → subject_id = f"ai-{model}"
    - has tool_name in metadata → subject_id = f"tool-{tool_name}"

    Args:
        message: Message to match

    Returns:
        Subject ID or None if no match
    """
    role = message.role
    metadata = message.metadata

    # User/human messages
    if role == "user":
        return "human-default"

    # Assistant messages - check for model info
    if role == "assistant":
        model = metadata.get("model")
        if model:
            # Normalize model name for subject ID
            model_id = model.replace(" ", "-").replace(".", "-").lower()
            return f"ai-{model_id}"

        # Check for tool usage
        tool_name = metadata.get("tool_name")
        if tool_name:
            return f"tool-{tool_name}"

        # Default assistant subject
        return "ai-assistant"

    # Tool messages
    tool_name = metadata.get("tool_name")
    if tool_name:
        return f"tool-{tool_name}"

    return None


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

    # Match subjects for messages
    for msg in messages:
        if msg.subject_id is None:
            msg.subject_id = match_subject_id(msg)

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
