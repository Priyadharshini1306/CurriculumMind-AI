"""Glue between Neo4j (mastery, structure, resources) and the pure gap/adaptive algorithms."""
import logging

from app.repositories import neo4j_repository as graph
from app.services import gap_service

log = logging.getLogger(__name__)


async def detect_and_store_gaps(user_id: str, course_id: str) -> list[dict]:
    """Knowledge-gap update: weak concepts -> their frontier prerequisites -> stored as HAS_GAP links."""
    structure = await graph.course_structure(course_id)
    mastery = await graph.mastery_map(user_id, course_id)
    gaps = gap_service.analyze(structure["concepts"], structure["edges"], mastery)
    await graph.save_gaps(user_id, course_id, gaps)
    return gaps


async def generate(user_id: str, course_id: str, hours_per_week: float) -> dict:
    structure = await graph.course_structure(course_id)
    mastery = await graph.mastery_map(user_id, course_id)
    gaps = gap_service.analyze(structure["concepts"], structure["edges"], mastery)
    resources = await graph.resources_top(course_id)
    path = gap_service.build_adaptive(structure["concepts"], structure["edges"], mastery, gaps, resources, hours_per_week)
    await graph.save_gaps(user_id, course_id, gaps)
    await graph.save_adaptive_path(user_id, course_id, [i for w in path["weeks"] for i in w["items"]])
    return {"gaps": gaps, **path}


async def preview(user_id: str, course_id: str, hours_per_week: float) -> dict:
    """Same result as generate() but read-only (dashboards must not rewrite the stored gaps and NEXT links)."""
    structure = await graph.course_structure(course_id)
    mastery = await graph.mastery_map(user_id, course_id)
    gaps = gap_service.analyze(structure["concepts"], structure["edges"], mastery)
    resources = await graph.resources_top(course_id)
    path = gap_service.build_adaptive(structure["concepts"], structure["edges"], mastery, gaps, resources, hours_per_week)
    return {"gaps": gaps, **path}
