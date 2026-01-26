import osmnx as ox

import config


def get_building_geometries():
    # Fetch building geometries from OSMnx
    gdf = ox.features_from_place(
        config.PLACE_NAME,
        {"building": True},
    )
    return gdf


def create_road_graph():
    # Add undirected OSMnx graph data to draw plugin
    graph = ox.graph.graph_from_place(
        config.PLACE_NAME,
        network_type="all",
        retain_all=True,
    ).to_undirected()
    return graph
