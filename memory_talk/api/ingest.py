"""Ingest API endpoints."""
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from jinja2 import Environment

from memory_talk.models import IngestRequest, Message, Subject
from memory_talk.storage import Storage

router = APIRouter(tags=["Ingest"])
storage = Storage()

# Jinja2 environment for evaluating match expressions
_jinja_env = Environment()


def evaluate_match_expr(match_expr: str, context: dict) -> bool:
    """Evaluate a Jinja2 match expression against message context.

    Args:
        match_expr: Jinja2 expression (e.g., "role == 'user'")
        context: Dictionary with message context (role, platform, etc.)

    Returns:
        True if the expression matches, False otherwise
    """
    try:
        # Add commonly used variables to context
        ctx = dict(context)
        template = _jinja_env.from_string("{{ " + match_expr + " }}")
        result = template.render(**ctx)
        # Evaluate as boolean
        return result.lower() in ("true", "1", "yes")
    except Exception:
        return False


def find_subject_by_match(message: Message, platform: str) -> str | None:
    """Find a matching subject based on message attributes and subject match rules.

    Args:
        message: The message to match
        platform: Platform name

    Returns:
        Subject ID if a match is found, None otherwise
    """
    # Get subjects with match expressions
    subjects = storage.list_subjects_with_match()

    # Build context for evaluation
    context = {
        "role": message.role,
        "platform": platform,
        "content": message.content,
    }

    # Add metadata fields to context if present
    if message.metadata:
        context.update(message.metadata)

    # Find first matching subject (already sorted by priority)
    for subject in subjects:
        if evaluate_match_expr(subject.match, context):
            return subject.id

    return None


def match_subject_id(message: Message, platform: str) -> str | None:
    """Match a subject_id for a message based on Subject match rules.

    Args:
        message: Message to match
        platform: Platform name

    Returns:
        Matched subject_id or None
    """
    return find_subject_by_match(message, platform)


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


@router.post("/api/v1/ingest")
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

    # Auto-match subject_id based on message attributes and Subject match rules
    for msg in messages:
        if msg.subject_id is None:
            msg.subject_id = match_subject_id(msg, request.platform)

    # Ensure all referenced subjects exist before saving
    ensure_subjects_exist(messages)

    storage.save_conversation(
        platform=request.platform,
        conversation_id=request.conversation_id,
        messages=messages,
        metadata=request.metadata,
    )

    return JSONResponse({"status": "ok", "conversation_id": request.conversation_id})


@router.post("/api/v1/ingest/blob")
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
