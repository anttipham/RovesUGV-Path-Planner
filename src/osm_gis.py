import geopandas as gpd
import osmnx as ox
import networkx as nx

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
    )
    return graph


def add_access_ways(
    graph: nx.MultiDiGraph, building_geometries: gpd.GeoDataFrame
) -> None:
    node_id = max(graph.nodes)
    access_ways: list[tuple[int, int, int, int]] = []
    # Find the nearest point to be used as access way for each building
    for centroid in building_geometries.centroid:
        node_id += 1
        # Distance to nearest node
        nearest_node = ox.distance.nearest_nodes(graph, centroid.x, centroid.y)
        access_ways.append((node_id, centroid.y, centroid.x, nearest_node))

    # Add the access ways to the graph
    for node1, y, x, node2 in access_ways:
        # Add building centroid to graph
        graph.add_node(node1, y=y, x=x)
        graph.add_edge(node1, node2)
        graph.add_edge(node2, node1)

    # Update edge length
    ox.distance.add_edge_lengths(graph)
