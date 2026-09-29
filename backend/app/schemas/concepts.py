from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RelType(str, Enum):
    PREREQUISITE_OF = "PREREQUISITE_OF"
    RELATED_TO = "RELATED_TO"


class Concept(BaseModel):
    id: str = ""
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=600)
    difficulty: int = Field(default=2, ge=1, le=5)
    estimated_minutes: int = Field(default=60, ge=5, le=1200)
    unit: str = ""
    topic: str = ""
    outcomes: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean(cls, v: str) -> str:
        return " ".join(v.split())


class Relationship(BaseModel):
    source: str  # concept id; for PREREQUISITE_OF this is the prerequisite
    target: str
    type: RelType = RelType.PREREQUISITE_OF
    confidence: float = Field(default=0.7, ge=0, le=1)
    evidence: str = ""


class ConceptGraph(BaseModel):
    concepts: list[Concept] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


# ---- LLM output shapes (names, not ids; converted + validated in the service) ----
class LLMConcept(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    difficulty: int = Field(default=2, ge=1, le=5)
    estimated_minutes: int = Field(default=60, ge=5, le=1200)
    topic: str = ""
    outcomes: list[str] = Field(default_factory=list)


class LLMUnitConcepts(BaseModel):
    concepts: list[LLMConcept] = Field(min_length=1)


class LLMRelationship(BaseModel):
    prerequisite: str
    dependent: str
    type: RelType = RelType.PREREQUISITE_OF
    confidence: float = Field(default=0.7, ge=0, le=1)
    evidence: str = ""


class LLMRelationships(BaseModel):
    relationships: list[LLMRelationship] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    curriculum_id: str


# ---- AI revision of an existing graph: the model returns only what changes, not the whole graph, so a revision
# call stays fast no matter how large the graph already is. See graph_service.apply_patch.
class GraphPatchConcept(BaseModel):
    id: str = ""  # an existing concept's id to modify it in place, or a fresh temporary id (e.g. "new1") to add one
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=600)
    difficulty: int = Field(default=2, ge=1, le=5)
    estimated_minutes: int = Field(default=60, ge=5, le=1200)
    unit: str = ""
    topic: str = ""
    outcomes: list[str] = Field(default_factory=list)


class GraphPatchRelationship(BaseModel):
    source: str  # a concept id, or an upserted concept's temporary id from this same response
    target: str
    type: RelType = RelType.PREREQUISITE_OF
    confidence: float = Field(default=0.7, ge=0, le=1)
    evidence: str = ""


class GraphPatch(BaseModel):
    upsert_concepts: list[GraphPatchConcept] = Field(default_factory=list)
    remove_concept_ids: list[str] = Field(default_factory=list)
    add_relationships: list[GraphPatchRelationship] = Field(default_factory=list)
    remove_relationships: list[GraphPatchRelationship] = Field(default_factory=list)
