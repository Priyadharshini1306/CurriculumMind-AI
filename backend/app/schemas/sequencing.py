from pydantic import BaseModel, Field


class PlanParams(BaseModel):
    hours_per_week: float = Field(default=8, ge=1, le=80)
    weeks_per_semester: int = Field(default=16, ge=2, le=30)


class Assignment(BaseModel):
    concept_id: str
    semester: int = Field(ge=1, le=20)
    week: int = Field(ge=1, le=30)  # week within the semester


class Plan(BaseModel):
    params: PlanParams = Field(default_factory=PlanParams)
    assignments: list[Assignment] = Field(default_factory=list)


class Violation(BaseModel):
    prerequisite: str
    concept: str
    reason: str


class OverloadedWeek(BaseModel):
    semester: int
    week: int
    hours: float
    capacity_hours: float


class PlanReport(BaseModel):
    violations: list[Violation]
    overloaded_weeks: list[OverloadedWeek]
    unassigned: list[str]
    unknown: list[str]
    duplicates: list[str]
    uncovered_outcomes: list[str]
    total_hours: float
    semesters: int

    @property
    def blocking(self) -> bool:
        return bool(self.violations or self.unknown or self.duplicates)


class GenerateRequest(BaseModel):
    curriculum_id: str
    params: PlanParams = Field(default_factory=PlanParams)
    feedback: str | None = Field(default=None, max_length=3000)


class VerifyRequest(BaseModel):
    curriculum_id: str
    plan: Plan | None = None


class RejectRequest(BaseModel):
    curriculum_id: str
    feedback: str = Field(default="", max_length=3000)
