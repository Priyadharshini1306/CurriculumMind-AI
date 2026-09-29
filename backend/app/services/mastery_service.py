"""Concept mastery from quiz performance.

    quiz score     = sum(points_i * difficulty_i) / sum(difficulty_i)       (harder questions count more)
    mastery (new)  = score                                   on the first attempt
                   = ALPHA * score + (1 - ALPHA) * previous  afterwards    (exponentially weighted: recent
                                                                              attempts matter most, one lucky or
                                                                              unlucky quiz cannot fully decide)
A concept is mastered at mastery >= MASTERY_THRESHOLD."""
from datetime import datetime, timezone

ALPHA = 0.6
MASTERY_THRESHOLD = 0.8
WEAK_THRESHOLD = 0.5


def weighted_score(points: list[float], difficulties: list[int]) -> float:
    if not points or len(points) != len(difficulties):
        raise ValueError("points and difficulties must be non-empty and equal in length")
    weights = [max(1, d) for d in difficulties]
    return sum(p * w for p, w in zip(points, weights)) / sum(weights)


def update(previous: float | None, score: float, alpha: float = ALPHA) -> float:
    score = min(1.0, max(0.0, score))
    if previous is None:
        return round(score, 4)
    return round(alpha * score + (1 - alpha) * previous, 4)


def is_mastered(mastery: float) -> bool:
    return mastery >= MASTERY_THRESHOLD


def classify(mastery: float | None) -> str:
    if mastery is None:
        return "NOT_STARTED"
    if mastery >= MASTERY_THRESHOLD:
        return "MASTERED"
    return "WEAK" if mastery < WEAK_THRESHOLD else "LEARNING"


def apply_attempt(previous: dict | None, points: list[float], difficulties: list[int]) -> dict:
    """previous: {mastery_score, attempt_count} or None. Returns the new mastery state."""
    score = weighted_score(points, difficulties)
    prev_score = previous["mastery_score"] if previous else None
    new = update(prev_score, score)
    return {"mastery_score": new, "attempt_count": (previous["attempt_count"] if previous else 0) + 1,
            "last_score": round(score, 4), "mastered": is_mastered(new),
            "last_updated": datetime.now(timezone.utc).isoformat()}
