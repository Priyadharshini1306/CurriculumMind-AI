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


def test_duplicate_units_collapsed():
    c = Curriculum.model_validate({"course": "X", "units": [{"title": "A"}, {"title": "a"}]})
    assert [u.title for u in c.units] == ["A"]


def test_blank_list_entries_dropped():
    c = Curriculum.model_validate({"course": "X", "units": [{"title": "A", "topics": ["", "T"]}, "", {"title": "B"}]})
    assert [u.title for u in c.units] == ["A", "B"]
    assert [t.title for t in c.units[0].topics] == ["T"]
