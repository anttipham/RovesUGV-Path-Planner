import osmnx as ox

import config


def create_road_graph():
    # Add undirected OSMnx graph data to draw plugin
    graph = ox.graph.graph_from_place(
        config.PLACE_NAME,
        network_type="all",
        retain_all=True,
    ).to_undirected()
    return graph
