import networkx as nx


def topological_order(g: nx.DiGraph) -> list[str]:
    """Deterministic topological order (ties broken by node id). Raises nx.NetworkXUnfeasible on cycles."""
    return list(nx.lexicographical_topological_sort(g, key=str))


def depth_levels(g: nx.DiGraph) -> dict[str, int]:
    """Longest prerequisite chain length ending at each node (0 = no prerequisites)."""
    depth: dict[str, int] = {}
    for n in topological_order(g):
        depth[n] = 1 + max((depth[p] for p in g.predecessors(n)), default=-1)
    return depth
