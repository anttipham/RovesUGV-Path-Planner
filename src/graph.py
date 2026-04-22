"""
Graph data access and graph preprocessing utilities.
"""

import geopandas as gpd
import networkx as nx
import osmnx as ox

import config


def get_building_gdf(G: nx.MultiDiGraph) -> None:
    """
    Fetch building polygons from OpenStreetMap inside the configured area.

    Notes
    -----
    Sets:
    - Graph attribute: `ugv_buildings` (building GeoDataFrame with OSM tags)
    """
    gdf = ox.features_from_polygon(
        config.AREA_POLYGON,
        {"building": True},
    )
    G.graph["ugv_buildings"] = gdf


def create_road_graph() -> nx.MultiDiGraph:
    """
    Create an unsimplified road graph for the configured area polygon.

    Returns
    -------
    nx.MultiDiGraph
        Directed multigraph containing OSM road/path network edges and nodes.
    """
    G = ox.graph.graph_from_polygon(
        config.AREA_POLYGON,
        network_type="all",
        truncate_by_edge=True,
        simplify=False,
    )
    return G


def add_custom_attributes(G: nx.MultiDiGraph) -> None:
    """
    Add application-specific attributes to graph edges and nodes.

    Added attributes
    ----------------
    Edge:
        ugv_sidewalk : bool
            True if edge is considered sidewalk-traversable.
    Node:
        ugv_crossing : bool
            True if node is tagged as a crossing.
    """
    # Ensure edge lengths exist (meters)
    ox.distance.add_edge_lengths(G)

    # Mark sidewalk-eligible edges for UGV routing
    for u, v, key, data in G.edges(keys=True, data=True):
        if (
            data.get("ugv_sidewalk") is True
            or data.get("foot") in config.SIDEWALK_FOOT_TAG_VALUES
        ):
            data["ugv_sidewalk"] = True
        else:
            data["ugv_sidewalk"] = False

    # Mark crossing nodes used for crossing penalties
    for node in G.nodes():
        if G.nodes[node].get("highway") == "crossing":
            G.nodes[node]["ugv_crossing"] = True

    # Roadway crossings should always be penalized, even if not tagged as crossings
    for node in G.nodes():
        roadways = [
            (u, v, key)
            for u, v, key, data in G.edges(node, keys=True, data=True)
            if not data.get("ugv_sidewalk", False)
        ]
        if len(roadways) > 2:
            G.nodes[node]["ugv_crossing"] = True
