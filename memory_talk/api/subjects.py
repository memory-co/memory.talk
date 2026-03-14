"""Subjects API endpoints."""
from fastapi import APIRouter, HTTPException

from memory_talk.models import Subject
from memory_talk.storage import Storage

router = APIRouter(tags=["Subjects"])
storage = Storage()


@router.get("/api/v1/subjects")
async def list_subjects() -> list[dict]:
    """List all subjects.

    Returns:
        List of subjects
    """
    subjects = storage.list_subjects()
    return [subject.model_dump(mode="json") for subject in subjects]


@router.get("/api/v1/subjects/{subject_id}")
async def get_subject(subject_id: str) -> dict:
    """Get a subject by ID.

    Args:
        subject_id: Subject ID

    Returns:
        Subject data
    """
    subject = storage.get_subject(subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject.model_dump(mode="json")


@router.post("/api/v1/subjects")
async def create_subject(subject: Subject) -> dict:
    """Create a new subject.

    Args:
        subject: Subject data

    Returns:
        Created subject
    """
    existing = storage.get_subject(subject.id)
    if existing:
        raise HTTPException(status_code=409, detail="Subject already exists")

    created = storage.create_subject(subject)
    return created.model_dump(mode="json")


@router.put("/api/v1/subjects/{subject_id}")
async def update_subject(subject_id: str, subject: Subject) -> dict:
    """Update a subject.

    Args:
        subject_id: Subject ID
        subject: Updated subject data

    Returns:
        Updated subject
    """
    if subject_id != subject.id:
        raise HTTPException(status_code=400, detail="Subject ID mismatch")

    updated = storage.update_subject(subject)
    if updated is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return updated.model_dump(mode="json")


@router.delete("/api/v1/subjects/{subject_id}")
async def delete_subject(subject_id: str) -> dict:
    """Delete a subject.

    Args:
        subject_id: Subject ID

    Returns:
        Success message
    """
    deleted = storage.delete_subject(subject_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"message": "Subject deleted successfully", "id": subject_id}
