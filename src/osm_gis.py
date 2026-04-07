"""
Everything related to OSMnx is here.
"""

import geopandas as gpd
import networkx as nx
import osmnx as ox

import config


# @st.cache_data
def get_building_gdf() -> gpd.GeoDataFrame:
    # Fetch building geometries from OSMnx
    gdf = ox.features_from_polygon(
        config.AREA_POLYGON,
        {"building": True},
    )
    return gdf


def create_road_graph() -> nx.MultiDiGraph:
    # Add undirected OSMnx graph data to draw plugin
    G = ox.graph.graph_from_polygon(
        config.AREA_POLYGON,
        network_type="all",
        # retain_all=True,
        truncate_by_edge=True,
        simplify=False,
    )
    return G
