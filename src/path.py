import networkx as nx


def add_weight(G: nx.MultiDiGraph):
    """
    TODO: Add weight for junctions
    """
    edge: dict
    for edge in G.edges.values():
        edge["weight"] = edge["length"]
        # Add more weight if the path is not for pedestrians
        if edge.get("foot") not in ("yes", "designated"):
            edge["weight"] *= 10


def add_centrality(G: nx.MultiDiGraph):
    # Calculate centrality for only buildings
    buildings = [
        node
        for node, is_building_access in G.nodes(data="building_access")
        if is_building_access
    ]
    centrality = nx.edge_betweenness_centrality_subset(
        G,
        sources=buildings,
        targets=buildings,
        weight="weight",
        # normalized=True,
    )
    for key, edge in G.edges.items():
        edge["centrality"] = centrality[key]
