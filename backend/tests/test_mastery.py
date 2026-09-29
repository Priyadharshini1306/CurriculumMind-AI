import pytest

from app.services import mastery_service as m


def test_weighted_score_favours_hard_questions():
    # got the easy question right, the hard one wrong
    assert m.weighted_score([1, 0], [1, 5]) == pytest.approx(1 / 6)
    # got the hard one right, the easy one wrong
    assert m.weighted_score([0, 1], [1, 5]) == pytest.approx(5 / 6)
    assert m.weighted_score([1, 1, 1], [1, 2, 3]) == 1.0


def test_weighted_score_validates_input():
    with pytest.raises(ValueError):
        m.weighted_score([], [])
    with pytest.raises(ValueError):
        m.weighted_score([1], [1, 2])


def test_first_attempt_is_the_score_then_ewma():
    assert m.update(None, 0.5) == 0.5
    assert m.update(0.5, 1.0) == pytest.approx(0.6 * 1.0 + 0.4 * 0.5)   # 0.8
    assert m.update(0.9, 0.0) == pytest.approx(0.36)                     # one bad quiz drags mastery down
    assert m.update(0.5, 7) == m.update(0.5, 1.0)                        # clamped to [0, 1]


def test_recent_performance_matters_more():
    improving = m.update(m.update(m.update(None, 0.2), 0.6), 1.0)
    declining = m.update(m.update(m.update(None, 1.0), 0.6), 0.2)
    assert improving > declining


def test_classification():
    assert m.classify(None) == "NOT_STARTED"
    assert m.classify(0.3) == "WEAK" and m.classify(0.6) == "LEARNING" and m.classify(0.8) == "MASTERED"


def test_apply_attempt_tracks_count_and_flag():
    s1 = m.apply_attempt(None, [1, 1], [2, 2])
    assert s1["mastery_score"] == 1.0 and s1["attempt_count"] == 1 and s1["mastered"]
    s2 = m.apply_attempt(s1, [0, 0], [2, 2])
    assert s2["attempt_count"] == 2 and s2["mastery_score"] == pytest.approx(0.4) and not s2["mastered"]
