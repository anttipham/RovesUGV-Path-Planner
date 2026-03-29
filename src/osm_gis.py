"""
Everything related to OSMnx is here.
"""

import geopandas as gpd
import networkx as nx
import osmnx as ox
import shapely
import streamlit as st

import config


# @st.cache_data
def get_building_gdf() -> gpd.GeoDataFrame:
    # Fetch building geometries from OSMnx
    gdf = ox.features_from_polygon(
        config.AREA_POLYGON,
        {"building": True},
    )
    return gdf


def _add_building_access_nodes(
    G: nx.MultiDiGraph, building_gdf: gpd.GeoDataFrame
) -> None:
    """
    TODO: Connect buildings to nearest edge
    """
    access_ways: dict[int, tuple[int, int, int]] = {}
    # Find the nearest point to be used as access way for each building
    for row in building_gdf.itertuples():
        id = row.Index[1]
        # Skip if the node already exists
        if id in G.nodes():
            continue

        # Add the centroid of a building as a node to the graph
        centroid = shapely.centroid(row.geometry)
        # Attach the centroid to the nearest node
        nearest_node = ox.distance.nearest_nodes(G, centroid.x, centroid.y)
        access_ways[id] = (nearest_node, centroid.y, centroid.x)

    # Add the access ways to the graph
    for node1, (node2, y, x) in access_ways.items():
        # Add building centroid to graph
        G.add_node(node1, y=y, x=x, building_access=True)
        G.add_edge(node1, node2, foot="yes")
        G.add_edge(node2, node1, foot="yes")

    # Update edge length
    ox.distance.add_edge_lengths(G)


# @st.cache_data
def create_road_graph() -> nx.MultiDiGraph:
    # Add undirected OSMnx graph data to draw plugin
    G = ox.graph.graph_from_polygon(
        config.AREA_POLYGON,
        network_type="all",
        # retain_all=True,
        truncate_by_edge=True,
        simplify=False,
    )
    _add_building_access_nodes(G, get_building_gdf())
    return G
