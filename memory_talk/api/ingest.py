"""Ingest API endpoints."""
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from memory_talk.models import IngestRequest, Message, Subject
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


def ensure_subjects_exist(messages: list[Message]) -> None:
    """Ensure all subjects referenced in messages exist.

    This creates any missing subjects before saving messages,
    since the messages table has a foreign key constraint on subject_id.

    Args:
        messages: List of messages to check for subject references
    """
    subject_ids = set()
    for msg in messages:
        if msg.subject_id:
            subject_ids.add(msg.subject_id)

    for subject_id in subject_ids:
        # Check if subject already exists
        existing = storage.get_subject(subject_id)
        if existing is None:
            # Create new subject
            name = subject_id
            if subject_id.startswith("ai-"):
                name = f"AI ({subject_id[3:]})"
            elif subject_id.startswith("tool-"):
                name = f"Tool ({subject_id[5:]})"

            subject = Subject(
                id=subject_id,
                name=name,
                metadata={"source": "auto-created"},
            )
            try:
                storage.create_subject(subject)
            except Exception:
                # Subject may have been created by another request
                pass


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

    # Ensure all referenced subjects exist before saving
    ensure_subjects_exist(messages)

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
