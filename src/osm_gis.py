import geopandas as gpd
import osmnx as ox
import osmnx.projection
import networkx as nx

# import streamlit as st

import config


# @st.cache_data
def get_building_gdf():
    # Fetch building geometries from OSMnx
    gdf = ox.features_from_place(
        config.PLACE_NAME,
        {"building": True},
    )
    return gdf


def _add_access_ways(graph: nx.MultiDiGraph, building_gdf: gpd.GeoDataFrame) -> None:
    """
    TODO: Add to the nearest edge, not node
    """
    node_id = max(graph.nodes)
    access_ways: dict[int, tuple[int, int, int]] = {}
    # Find the nearest point to be used as access way for each building
    # The for loop could be simplified to `for centroid in building_gdf.centroid:`,
    # but this results in a warning.
    for centroid in osmnx.projection.project_gdf(building_gdf).centroid.to_crs(
        crs=building_gdf.crs
    ):
        node_id += 1
        # Distance to nearest node
        nearest_node = ox.distance.nearest_nodes(graph, centroid.x, centroid.y)
        access_ways[node_id] = (nearest_node, centroid.y, centroid.x)

    # Add the access ways to the graph
    for node1, (node2, y, x) in access_ways.items():
        # Add building centroid to graph
        graph.add_node(node1, y=y, x=x, building_access=True)
        graph.add_edge(node1, node2, foot="yes")
        graph.add_edge(node2, node1, foot="yes")

    # Update edge length
    ox.distance.add_edge_lengths(graph)


# @st.cache_data
def create_road_graph():
    # Add undirected OSMnx graph data to draw plugin
    graph = ox.graph.graph_from_place(
        config.PLACE_NAME,
        network_type="all",
        retain_all=True,
        simplify=False,
    )
    _add_access_ways(graph, get_building_gdf())
    return graph
