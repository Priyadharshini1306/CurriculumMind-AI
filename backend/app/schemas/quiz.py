from enum import Enum

from pydantic import BaseModel, Field


class QType(str, Enum):
    MCQ = "MCQ"
    TRUE_FALSE = "TRUE_FALSE"
    MULTI = "MULTI"


# ---- what the LLM returns (lenient; each question is validated individually afterwards) ----
class LLMQuestion(BaseModel):
    question: str = ""
    type: str = "MCQ"
    options: list[str] = Field(default_factory=list)
    correct: list[int] = Field(default_factory=list)  # 0-based indices into options
    explanation: str = ""
    difficulty: int = 2


class LLMQuiz(BaseModel):
    questions: list[LLMQuestion] = Field(min_length=1)


# ---- validated question as stored ----
class Question(BaseModel):
    id: str = ""
    question: str
    type: QType
    options: list[str]
    correct: list[int]
    explanation: str
    difficulty: int = Field(ge=1, le=5)
    outcome: str | None = None


class QuestionPublic(BaseModel):
    """What a learner sees before submitting: never includes the answers."""
    id: str
    question: str
    type: QType
    options: list[str]
    difficulty: int
    outcome: str | None = None
    multiple: bool = False


class QuizPublic(BaseModel):
    quiz_id: str
    concept_id: str
    concept: str
    questions: list[QuestionPublic]


class GenerateRequest(BaseModel):
    curriculum_id: str
    concept_ids: list[str] = Field(min_length=1, max_length=6)
    num_questions: int = Field(default=4, ge=3, le=8)
    regenerate: bool = False


class SubmitRequest(BaseModel):
    quiz_id: str
    answers: dict[str, list[int]]  # question_id -> selected option indices


class QuestionResult(BaseModel):
    question_id: str
    question: str
    selected: list[int]
    correct: list[int]
    points: float
    explanation: str
    options: list[str]
    outcome: str | None = None
