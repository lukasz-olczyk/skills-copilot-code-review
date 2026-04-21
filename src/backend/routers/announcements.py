"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _parse_datetime(value: str, field_name: str) -> datetime:
    """Parse an ISO datetime string into a timezone-aware datetime object."""
    try:
        normalized_value = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Expected ISO datetime format."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def _verify_signed_in_user(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Ensure the provided username belongs to an existing teacher account."""
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize database documents for API responses."""
    return {
        "id": announcement.get("_id"),
        "title": announcement.get("title", ""),
        "content": announcement.get("content", ""),
        "start_date": announcement.get("start_date"),
        "expires_at": announcement.get("expires_at"),
        "created_at": announcement.get("created_at"),
        "updated_at": announcement.get("updated_at")
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def list_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements active at the current time for public display."""
    now = datetime.now(timezone.utc)

    active_announcements: List[Dict[str, Any]] = []
    for announcement in announcements_collection.find().sort("expires_at", 1):
        expires_at_raw = announcement.get("expires_at")
        if not expires_at_raw:
            continue

        expires_at = _parse_datetime(expires_at_raw, "expires_at")
        start_date_raw = announcement.get("start_date")
        start_date = _parse_datetime(start_date_raw, "start_date") if start_date_raw else None

        is_started = start_date is None or start_date <= now
        is_not_expired = now <= expires_at

        if is_started and is_not_expired:
            active_announcements.append(_serialize_announcement(announcement))

    return active_announcements


@router.get("/manage", response_model=List[Dict[str, Any]])
def list_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Return all announcements for authenticated users who manage them."""
    _verify_signed_in_user(teacher_username)

    return [
        _serialize_announcement(announcement)
        for announcement in announcements_collection.find().sort("created_at", -1)
    ]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    title: str,
    content: str,
    expires_at: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement with a required expiration date."""
    _verify_signed_in_user(teacher_username)

    clean_title = title.strip()
    clean_content = content.strip()

    if not clean_title:
        raise HTTPException(status_code=400, detail="Title is required")
    if not clean_content:
        raise HTTPException(status_code=400, detail="Content is required")

    expires_at_dt = _parse_datetime(expires_at, "expires_at")
    start_date_dt = _parse_datetime(start_date, "start_date") if start_date else None

    if start_date_dt and start_date_dt >= expires_at_dt:
        raise HTTPException(status_code=400, detail="Start date must be before expiration date")

    now_iso = datetime.now(timezone.utc).isoformat()
    announcement_id = str(uuid4())

    new_announcement = {
        "_id": announcement_id,
        "title": clean_title,
        "content": clean_content,
        "start_date": start_date_dt.isoformat() if start_date_dt else None,
        "expires_at": expires_at_dt.isoformat(),
        "created_at": now_iso,
        "updated_at": now_iso
    }

    announcements_collection.insert_one(new_announcement)

    return _serialize_announcement(new_announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    title: str,
    content: str,
    expires_at: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement."""
    _verify_signed_in_user(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    clean_title = title.strip()
    clean_content = content.strip()

    if not clean_title:
        raise HTTPException(status_code=400, detail="Title is required")
    if not clean_content:
        raise HTTPException(status_code=400, detail="Content is required")

    expires_at_dt = _parse_datetime(expires_at, "expires_at")
    start_date_dt = _parse_datetime(start_date, "start_date") if start_date else None

    if start_date_dt and start_date_dt >= expires_at_dt:
        raise HTTPException(status_code=400, detail="Start date must be before expiration date")

    updates = {
        "title": clean_title,
        "content": clean_content,
        "start_date": start_date_dt.isoformat() if start_date_dt else None,
        "expires_at": expires_at_dt.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    announcements_collection.update_one({"_id": announcement_id}, {"$set": updates})

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement by id."""
    _verify_signed_in_user(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
