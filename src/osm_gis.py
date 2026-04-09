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


def add_custom_attributes(G: nx.MultiDiGraph) -> None:
    ox.distance.add_edge_lengths(G)

    # Add ugv_access attribute to edges where foot access is allowed
    for u, v, key, data in G.edges(keys=True, data=True):
        if data.get("ugv_access") == True or data.get("foot") in config.SIDEWALK_FOOT_TAG_VALUES:
            data["ugv_access"] = True
        else:
            data["ugv_access"] = False

    # Find all crossings where sidewalks intersect with roadways by checking
    # neighboring edge attributes
    for node in G.nodes():
        # Flawed logic. Does not account for cases where the service road is on top of
        # the sidewalk.
        # ugv_access_attributes = set()
        # for _, _, _, data in G.out_edges(node, keys=True, data=True, default=False):
        #     if data.get("virtual") or data.get("temporary_connection"):
        #         continue
        #     ugv_access_attributes.add(data["ugv_access"])

        # if len(ugv_access_attributes) > 1:
        #     G.nodes[node]["ugv_crossing"] = True
        # else:
        #     G.nodes[node]["ugv_crossing"] = False
        if G.nodes[node].get("highway") == "crossing":
            G.nodes[node]["ugv_crossing"] = True
