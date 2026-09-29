"""Curriculum extraction (from a syllabus or a learning goal) and feedback-driven revision."""
import json

from app.schemas.curriculum import Curriculum
from app.services import llm_service
from app.services.llm_service import LLMError

MAX_SYLLABUS_CHARS = 14000

EXTRACT_SYSTEM = (
    "You are an expert curriculum analyst. Extract the structured curriculum from the syllabus text. "
    "Use only information present in the text; leave fields null or empty if absent -- EXCEPT \"course\", "
    "which must never be empty: if no explicit course title is stated, write a short descriptive title "
    "yourself from the subject matter (e.g. the department/topic covered), never an empty string. "
    "Extract: course name, course code, curriculum version/year, credit hours, semester, learning outcomes, "
    "explicit prerequisites, units (with hours/weeks if given), topics per unit, and subtopics per topic. "
    "If a unit lists no topics, create sensible topics from its title."
)

GOAL_SYSTEM = (
    "You are an expert curriculum designer. Interpret the learner's goal: identify the domain, target level and "
    "expected skills, then draft a curriculum: a course name, learning outcomes, and an ordered list of units, "
    "each with topics and subtopics, progressing from foundations to the target level. "
    "Respect the stated duration and weekly hours when choosing scope."
)

REVISE_SYSTEM = (
    "You revise a curriculum according to human feedback. Apply the feedback faithfully, keep everything the "
    "feedback does not mention unchanged, and return the complete revised curriculum."
)

# A compact worked example, not the verbose auto-generated JSON schema: the full schema for a recursive,
# array-of-objects shape like this confuses the model into emitting malformed units (e.g. "" instead of an object).
CURRICULUM_HINT = (
    'Reply with JSON only, in this shape:\n'
    '{"course":"...","course_code":null,"version":null,"credit_hours":null,"semester":null,'
    '"outcomes":["..."],"explicit_prerequisites":["..."],'
    '"units":[{"title":"...","hours":null,"weeks":null,"topics":[{"title":"...","subtopics":["..."]}]}]}'
)
CURRICULUM_NUM_PREDICT = 3000


def _fallback_title(text: str) -> str:
    """Best-effort course title when the model won't supply one: syllabuses conventionally open with it."""
    for line in text.splitlines():
        line = line.strip(" \t-#*")
        if 3 <= len(line) <= 120:
            return line
    return "Untitled Course"


async def from_syllabus(text: str) -> Curriculum:
    snippet = f"SYLLABUS:\n{text[:MAX_SYLLABUS_CHARS]}"
    try:
        return await llm_service.generate_json(
            EXTRACT_SYSTEM, snippet, Curriculum,
            schema_hint=CURRICULUM_HINT, num_predict=CURRICULUM_NUM_PREDICT)
    except LLMError as e:
        # The one failure mode worth a hard safety net: the model left "course" empty despite instructions.
        # Anything else (rate limits, malformed JSON elsewhere) should still surface as a real failure.
        if "course" not in str(e) or "string_too_short" not in str(e):
            raise
        fallback = _fallback_title(text)
        user = (f"{snippet}\n\nYour previous answer left \"course\" empty, which is invalid -- it must never be "
                f"empty. Use \"{fallback}\" unless you can infer a better title from the text.")
        return await llm_service.generate_json(
            EXTRACT_SYSTEM, user, Curriculum, schema_hint=CURRICULUM_HINT, num_predict=CURRICULUM_NUM_PREDICT)


async def from_goal(goal: dict) -> Curriculum:
    details = {k: v for k, v in goal.items() if k in
               ("goal", "domain", "target_level", "duration", "hours_per_week", "existing_knowledge") and v}
    return await llm_service.generate_json(GOAL_SYSTEM, json.dumps(details), Curriculum, temperature=0.4,
                                            schema_hint=CURRICULUM_HINT, num_predict=CURRICULUM_NUM_PREDICT)


async def revise(current: Curriculum, feedback: str) -> Curriculum:
    user = f"CURRENT CURRICULUM:\n{current.model_dump_json()}\n\nFEEDBACK:\n{feedback}"
    return await llm_service.generate_json(REVISE_SYSTEM, user, Curriculum,
                                            schema_hint=CURRICULUM_HINT, num_predict=CURRICULUM_NUM_PREDICT)
