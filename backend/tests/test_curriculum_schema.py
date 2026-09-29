import pytest
from pydantic import ValidationError

from app.schemas.curriculum import Curriculum


def test_valid_and_cleaned():
    c = Curriculum.model_validate({"course": "  Java   Programming ", "units": [
        {"title": "Unit 1", "topics": [{"title": "Basics", "subtopics": ["Vars", "vars", " Types "]}]}]})
    assert c.course == "Java Programming"
    assert c.units[0].topics[0].subtopics == ["Vars", "Types"]


def test_requires_units():
    with pytest.raises(ValidationError):
        Curriculum.model_validate({"course": "X", "units": []})


def test_duplicate_units_rejected():
    with pytest.raises(ValidationError):
        Curriculum.model_validate({"course": "X", "units": [{"title": "A"}, {"title": "a"}]})
