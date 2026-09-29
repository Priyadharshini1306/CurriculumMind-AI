import random

from app.schemas.quiz import LLMQuestion, QType, Question
from app.services import quiz_service as qs


def llm(**kw):
    base = {"question": "What does HashMap use to find a bucket?", "type": "MCQ",
            "options": ["hashCode", "toString", "equals only", "size"], "correct": [0],
            "explanation": "hashCode picks the bucket.", "difficulty": 2}
    return LLMQuestion(**{**base, **kw})


def test_valid_mcq_true_false_multi():
    assert qs.clean_question(llm()).type == QType.MCQ
    tf = qs.clean_question(llm(type="true_false", options=["yes", "no"], correct=[1]))
    assert tf.options == ["True", "False"] and tf.correct == [1]
    multi = qs.clean_question(llm(type="MULTI", correct=[0, 2]))
    assert multi.type == QType.MULTI and multi.correct == [0, 2]


def test_invalid_questions_are_rejected():
    assert qs.clean_question(llm(correct=[7])) is None                       # index out of range
    assert qs.clean_question(llm(options=["a", "a", "b", "c"])) is None       # duplicate options
    assert qs.clean_question(llm(explanation="")) is None                    # no explanation
    assert qs.clean_question(llm(type="essay")) is None                      # unknown type
    assert qs.clean_question(llm(type="MULTI", correct=[0, 1, 2, 3])) is None  # all options correct
    assert qs.clean_question(llm(question="Hi?")) is None                   # too short


def test_common_model_mistakes_are_repaired_not_dropped():
    # single-choice question with two correct answers is really a multiple-answer question
    q = qs.clean_question(llm(correct=[0, 1]))
    assert q.type == QType.MULTI and q.correct == [0, 1]
    # multiple-answer question with only one correct answer is really single choice
    q = qs.clean_question(llm(type="MULTI", correct=[2]))
    assert q.type == QType.MCQ and q.correct == [2]
    # ... but not when it cannot be a valid multiple-answer question (every option correct)
    assert qs.clean_question(llm(correct=[0, 1, 2, 3])) is None


def test_shuffle_keeps_correct_answer_content():
    q = qs.clean_question(llm(type="MULTI", correct=[0, 2]))
    right = {q.options[i] for i in q.correct}
    s = qs.shuffle_options(q, random.Random(1))
    assert {s.options[i] for i in s.correct} == right and sorted(s.options) == sorted(q.options)


def question(qtype, correct, n=4):
    return Question(id="q1", question="text text", type=qtype, options=[f"o{i}" for i in range(n)],
                    correct=correct, explanation="e", difficulty=2)


def test_grading_single_answer():
    q = question(QType.MCQ, [1])
    assert qs.points_for(q, [1]) == 1.0 and qs.points_for(q, [0]) == 0.0 and qs.points_for(q, []) == 0.0
    assert qs.points_for(q, [1, 2]) == 0.0


def test_grading_multi_partial_credit():
    q = question(QType.MULTI, [0, 1])
    assert qs.points_for(q, [0, 1]) == 1.0
    assert qs.points_for(q, [0]) == 0.5
    assert qs.points_for(q, [0, 3]) == 0.0      # one right, one wrong -> no credit
    assert qs.points_for(q, [2, 3]) == 0.0


def test_grade_totals_and_ignores_invalid_indices():
    qa, qb = question(QType.MCQ, [0]), question(QType.MULTI, [0, 1])
    qb = qb.model_copy(update={"id": "q2"})
    g = qs.grade([qa, qb], {"q1": [0], "q2": [0, 99]})
    assert g["score"] == 1.5 and g["total"] == 2 and g["percent"] == 75
    assert g["results"][1].selected == [0]


def test_public_view_hides_answers():
    p = qs.public(question(QType.MULTI, [0, 1]))
    assert "correct" not in p.model_dump() and "explanation" not in p.model_dump() and p.multiple
