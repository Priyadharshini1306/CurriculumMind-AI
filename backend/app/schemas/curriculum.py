from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def _clean(s: str) -> str:
    return " ".join(s.split())


def _lenient_items(v):
    """LLMs sometimes pad object lists with "" / null, or give a bare string where an object belongs. Drop the blanks
    and wrap bare strings as {"title": ...} so one glitchy entry doesn't fail the whole curriculum."""
    if not isinstance(v, list):
        return v
    out = []
    for item in v:
        if isinstance(item, str):
            item = item.strip()
            if item:
                out.append({"title": item})
        elif item:
            out.append(item)
    return out


class Topic(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subtopics: list[str] = Field(default_factory=list)

    _t = field_validator("title")(_clean)

    @field_validator("subtopics", mode="before")
    @classmethod
    def drop_blank_subs(cls, v):
        if not isinstance(v, list):
            return v
        return [s for s in v if isinstance(s, str) and s.strip()]

    @field_validator("subtopics")
    @classmethod
    def clean_subs(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for s in v:
            s = _clean(s)
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out


class Unit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    hours: float | None = Field(default=None, ge=0, le=500)
    weeks: int | None = Field(default=None, ge=0, le=60)
    topics: list[Topic] = Field(default_factory=list)

    _t = field_validator("title")(_clean)
    _lenient_topics = field_validator("topics", mode="before")(_lenient_items)


class Curriculum(BaseModel):
    course: str = Field(min_length=1, max_length=200)
    course_code: str | None = None
    version: str | None = Field(default=None, description="Curriculum version/year, e.g. 2025")
    credit_hours: float | None = Field(default=None, ge=0, le=60)
    semester: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    explicit_prerequisites: list[str] = Field(default_factory=list)
    units: list[Unit] = Field(min_length=1)

    _c = field_validator("course")(_clean)
    _lenient_units = field_validator("units", mode="before")(_lenient_items)

    @field_validator("units")
    @classmethod
    def unique_units(cls, v: list[Unit]) -> list[Unit]:
        seen, out = set(), []
        for u in v:
            if u.title.lower() not in seen:
                seen.add(u.title.lower())
                out.append(u)
        return out


class DraftStatus(str, Enum):
    EXTRACTING = "EXTRACTING"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"


class ExtractRequest(BaseModel):
    upload_id: str | None = None
    goal_id: str | None = None


class VerifyRequest(BaseModel):
    curriculum_id: str
    curriculum: Curriculum  # the (possibly human-edited) curriculum being approved


class ReviseRequest(BaseModel):
    curriculum_id: str
    feedback: str = Field(min_length=3, max_length=3000)
    curriculum: Curriculum | None = None  # current edits, if any; else the stored draft is used


class DraftOut(BaseModel):
    id: str
    source: str
    status: DraftStatus
    error: str | None = None
    revision: int = 0
    curriculum: Curriculum | None = None
    created_at: datetime
