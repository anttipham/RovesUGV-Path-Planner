"""
Everything related to fetching data for the graph is here.
"""

import geopandas as gpd
import networkx as nx
import osmnx as ox

import config


def get_building_gdf() -> gpd.GeoDataFrame:
    # Fetch building geometries from OSMnx
    gdf = ox.features_from_polygon(
        config.AREA_POLYGON,
        {"building": True},
    )
    return gdf


def create_road_graph() -> nx.MultiDiGraph:
    G = ox.graph.graph_from_polygon(
        config.AREA_POLYGON,
        network_type="all",
        # retain_all=True,
        truncate_by_edge=True,
        simplify=False,
    )
    return G


def add_custom_attributes(G: nx.MultiDiGraph) -> None:
    ox.distance.add_edge_lengths(G)

    # Add ugv_sidewalk attribute to edges where foot access is allowed
    for u, v, key, data in G.edges(keys=True, data=True):
        if (
            data.get("ugv_sidewalk") == True
            or data.get("foot") in config.SIDEWALK_FOOT_TAG_VALUES
        ):
            data["ugv_sidewalk"] = True
        else:
            data["ugv_sidewalk"] = False

    # Find all crossings and add a custom attribute to the nodes
    for node in G.nodes():
        if G.nodes[node].get("highway") == "crossing":
            G.nodes[node]["ugv_crossing"] = True
