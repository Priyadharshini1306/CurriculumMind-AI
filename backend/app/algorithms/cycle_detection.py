import networkx as nx


def build_digraph(concept_ids: list[str], prereq_edges: list[tuple[str, str]]) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(concept_ids)
    g.add_edges_from(prereq_edges)
    return g


def find_cycles(g: nx.DiGraph, limit: int = 20) -> list[list[str]]:
    """Return up to `limit` simple cycles (each as a list of node ids)."""
    cycles = []
    for c in nx.simple_cycles(g):
        cycles.append(c)
        if len(cycles) >= limit:
            break
    return cycles


def is_dag(g: nx.DiGraph) -> bool:
    return nx.is_directed_acyclic_graph(g)


def redundant_edges(g: nx.DiGraph) -> list[tuple[str, str]]:
    """Transitive edges: (a, c) is redundant if another path a -> ... -> c exists. Only defined for DAGs."""
    if not is_dag(g):
        return []
    reduced = nx.transitive_reduction(g)
    return sorted(e for e in g.edges if not reduced.has_edge(*e))
