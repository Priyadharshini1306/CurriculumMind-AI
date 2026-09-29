"""Quiz generation (LLM, validated and repaired question by question), option shuffling and grading."""
import json
import logging
import random

from app.schemas.quiz import LLMQuestion, LLMQuiz, QType, Question, QuestionPublic, QuestionResult
from app.services import llm_service

log = logging.getLogger(__name__)
MIN_VALID_QUESTIONS = 3
DEFAULT_QUESTIONS = 4

# Kept short and fixed on purpose: fewer prompt tokens means faster, cheaper Groq calls.
QUIZ_SYSTEM = (
    "You write short quiz questions that test one concept. Use only the concept and key points given.\n"
    "Rules: type is MCQ (4 options, exactly 1 correct), TRUE_FALSE (options [\"True\",\"False\"], 1 correct) or "
    "MULTI (4 options, 2 or 3 correct). 'correct' lists 0-based option indices. Keep every option under 10 words and "
    "every explanation under 20 words. difficulty is 1 (easy) to 5 (hard)."
)
QUIZ_HINT = (
    'Reply with JSON only, in this shape:\n'
    '{"questions":[{"question":"...","type":"MCQ","options":["a","b","c","d"],"correct":[1],'
    '"explanation":"one short sentence","difficulty":2}]}'
)


def clean_question(q: LLMQuestion) -> Question | None:
    """Validate one LLM question, repairing the mistakes small models make most often; None if unusable."""
    text = " ".join(q.question.split())
    opts = [" ".join(str(o).split()) for o in q.options]
    kind = q.type.strip().upper().replace("-", "_").replace(" ", "_")
    kind = {"MULTIPLE_CHOICE": "MCQ", "TF": "TRUE_FALSE", "BOOLEAN": "TRUE_FALSE",
            "MULTIPLE_ANSWER": "MULTI", "MULTI_SELECT": "MULTI", "MULTIPLE_SELECT": "MULTI"}.get(kind, kind)
    if kind not in QType.__members__ or len(text) < 8 or not q.explanation.strip():
        return None
    qt = QType[kind]
    correct = sorted(set(q.correct))
    if qt == QType.TRUE_FALSE:
        opts = ["True", "False"]
    if len(set(o.lower() for o in opts)) != len(opts) or any(not o for o in opts):
        return None
    if not correct or any(i < 0 or i >= len(opts) for i in correct):
        return None
    # repair: a "single choice" question with several correct options is really a multiple-answer question, and
    # a multiple-answer question with one correct option is really single choice
    if qt == QType.MCQ and len(correct) >= 2 and 4 <= len(opts) <= 5 and len(correct) < len(opts):
        qt = QType.MULTI
    elif qt == QType.MULTI and len(correct) == 1 and 3 <= len(opts) <= 5:
        qt = QType.MCQ
    if qt == QType.MCQ and (not 3 <= len(opts) <= 5 or len(correct) != 1):
        return None
    if qt == QType.TRUE_FALSE and len(correct) != 1:
        return None
    if qt == QType.MULTI and not (4 <= len(opts) <= 5 and 2 <= len(correct) < len(opts)):
        return None
    return Question(question=text, type=qt, options=opts, correct=correct,
                    explanation=" ".join(q.explanation.split()), difficulty=min(5, max(1, q.difficulty)))


def shuffle_options(q: Question, rng: random.Random) -> Question:
    """LLMs tend to put the right answer first; shuffle (True/False keeps its natural order)."""
    if q.type == QType.TRUE_FALSE:
        return q
    order = list(range(len(q.options)))
    rng.shuffle(order)
    return q.model_copy(update={"options": [q.options[i] for i in order],
                                "correct": sorted(order.index(c) for c in q.correct)})


def _prompt(course: str, concept: dict, n: int) -> str:
    points = "; ".join(concept.get("required_points") or [])
    mix = {3: "2 MCQ, 1 TRUE_FALSE", 4: "2 MCQ, 1 TRUE_FALSE, 1 MULTI",
           5: "3 MCQ, 1 TRUE_FALSE, 1 MULTI"}.get(n, f"{n} questions of mixed types")
    return (f"Course: {course}\nConcept: {concept['name']}\nDescription: {concept.get('description', '')}\n"
            f"Key points: {points or 'n/a'}\nWrite {n} questions ({mix}).")


async def generate_questions(course: str, concept: dict, n: int = DEFAULT_QUESTIONS) -> list[Question]:
    last_err = ""
    for attempt in range(2):
        try:
            # ask for one spare question: the model's occasional unusable one then does not leave the quiz short
            res = await llm_service.generate_json(
                QUIZ_SYSTEM, _prompt(course, concept, n + 1), LLMQuiz, temperature=0.4, retries=0,
                schema_hint=QUIZ_HINT, num_ctx=3072, num_predict=1800)
        except llm_service.LLMError as e:
            # gpt-oss's hidden reasoning tokens count against num_predict and vary widely, so an occasional call
            # still comes back empty -- worth a second try here rather than failing the whole quiz on one bad call
            last_err = str(e)
            log.warning("quiz generation for %s: %s", concept["name"], last_err)
            continue
        questions = [c for q in res.questions if (c := clean_question(q))]
        if len(questions) >= min(MIN_VALID_QUESTIONS, n):
            rng = random.Random(f"{concept['id']}:{attempt}")
            outcome = (concept.get("outcomes") or [None])[0]
            out = []
            for i, q in enumerate(questions[:n]):
                q = shuffle_options(q, rng)
                out.append(q.model_copy(update={"id": f"{concept['id']}:q:{i}", "outcome": outcome}))
            return out
        last_err = f"only {len(questions)} usable questions"
        log.warning("quiz generation for %s: %s", concept["name"], last_err)
    raise llm_service.LLMError(f"Could not generate a valid quiz for '{concept['name']}' ({last_err})")


def public(q: Question) -> QuestionPublic:
    return QuestionPublic(id=q.id, question=q.question, type=q.type, options=q.options, difficulty=q.difficulty,
                          outcome=q.outcome, multiple=q.type == QType.MULTI)


def points_for(q: Question, selected: list[int]) -> float:
    sel, correct = set(selected), set(q.correct)
    if q.type == QType.MULTI:  # partial credit, penalising wrong picks
        return max(0.0, (len(sel & correct) - len(sel - correct)) / len(correct))
    return 1.0 if sel == correct else 0.0


def grade(questions: list[Question], answers: dict[str, list[int]]) -> dict:
    results = []
    for q in questions:
        sel = sorted({i for i in answers.get(q.id, []) if 0 <= i < len(q.options)})
        results.append(QuestionResult(question_id=q.id, question=q.question, selected=sel, correct=q.correct,
                                      points=round(points_for(q, sel), 3), explanation=q.explanation,
                                      options=q.options, outcome=q.outcome))
    total = len(questions)
    score = round(sum(r.points for r in results), 2)
    return {"score": score, "total": total, "percent": round(100 * score / total) if total else 0,
            "results": results}
