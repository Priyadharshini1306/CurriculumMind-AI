from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class UploadStatus(str, Enum):
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class UploadOut(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    status: UploadStatus
    error: str | None = None
    text_chars: int = 0
    curriculum_id: str | None = None  # set once the syllabus text has been turned into a course draft
    uploaded_at: datetime


class UploadDetail(UploadOut):
    text: str | None = None


class GoalRequest(BaseModel):
    goal: str = Field(min_length=5, max_length=2000)
    domain: str | None = Field(default=None, max_length=100)
    target_level: str | None = Field(default=None, max_length=50)
    duration: str | None = Field(default=None, max_length=50)
    hours_per_week: int | None = Field(default=None, ge=1, le=80)
    existing_knowledge: str | None = Field(default=None, max_length=1000)


class GoalOut(GoalRequest):
    id: str
    curriculum_id: str | None = None
    created_at: datetime
