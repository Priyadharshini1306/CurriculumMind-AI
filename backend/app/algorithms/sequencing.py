"""Semester/week allocation over the prerequisite DAG.

1. Topological sort (prerequisites first), keeping units together: ties are broken by unit order, then difficulty.
2. Difficulty-weighted effort estimate per concept.
3. Greedy packing into weeks bounded by weekly study hours.
4. Weeks grouped into semesters of `weeks_per_semester`.
"""
from dataclasses import dataclass

import networkx as nx

DIFFICULTY_FACTOR = {1: 0.9, 2: 1.0, 3: 1.1, 4: 1.25, 5: 1.4}


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    difficulty: int
    minutes: int
    unit_index: int


def effort_minutes(item: Item) -> float:
    return item.minutes * DIFFICULTY_FACTOR.get(item.difficulty, 1.0)


def topological_sequence(items: list[Item], prereq_edges: list[tuple[str, str]]) -> list[Item]:
    by_id = {i.id: i for i in items}
    g = nx.DiGraph()
    g.add_nodes_from(by_id)
    g.add_edges_from(e for e in prereq_edges if e[0] in by_id and e[1] in by_id and e[0] != e[1])
    order = nx.lexicographical_topological_sort(
        g, key=lambda n: (by_id[n].unit_index, by_id[n].difficulty, by_id[n].name, n))
    return [by_id[n] for n in order]  # raises NetworkXUnfeasible if the graph has a cycle


def allocate(sequence: list[Item], hours_per_week: float, weeks_per_semester: int) -> list[tuple[str, int, int]]:
    """Return (concept_id, semester, week_in_semester) for each item, in sequence order."""
    capacity = hours_per_week * 60
    out, week_index, used = [], 0, 0.0
    for item in sequence:
        cost = effort_minutes(item)
        if used > 0 and used + cost > capacity:
            week_index += 1
            used = 0.0
        used += cost
        out.append((item.id, week_index // weeks_per_semester + 1, week_index % weeks_per_semester + 1))
    return out
