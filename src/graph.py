"""
Graph data access and graph preprocessing utilities.
"""

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pyproj
from shapely.geometry import LineString

import config

# def add_building_gdf(G: nx.MultiDiGraph) -> None:
#     """
#     Fetch building polygons from OpenStreetMap inside the configured area.

#     Notes
#     -----
#     Sets:
#     - Graph attribute: `ugv_buildings` (building GeoDataFrame with OSM tags)
#     """
#     gdf = ox.features_from_polygon(
#         config.AREA_POLYGON,
#         {"building": True},
#     )
#     G.graph["ugv_buildings"] = gdf


def create_road_graph() -> nx.MultiDiGraph:
    """
    Create an unsimplified road graph from the local warehouse GeoJSON.

    Returns
    -------
    nx.MultiDiGraph
        Directed multigraph containing road/path network edges and nodes.
    """
    gdf = gpd.read_file(config.WAREHOUSE_NETWORK_GEOJSON_PATH)
    if gdf.empty:
        raise ValueError(
            f"No features found in {config.WAREHOUSE_NETWORK_GEOJSON_PATH}."
        )

    if gdf.crs is None:
        gdf = gdf.set_crs(config.MAP_EPSG)
    else:
        gdf = gdf.to_crs(config.MAP_EPSG)

    gdf = gdf[gdf.geometry.type.isin(["LineString", "MultiLineString"])].explode(
        index_parts=False
    )
    if gdf.empty:
        raise ValueError(
            "Warehouse network GeoJSON does not contain LineString geometries."
        )

    G = nx.MultiDiGraph()
    G.graph["crs"] = config.MAP_EPSG

    to_metric = pyproj.Transformer.from_crs(
        config.MAP_EPSG,
        config.METRIC_EPSG,
        always_xy=True,
    )

    coord_to_node: dict[tuple[float, float], int] = {}
    next_node_id = 0

    def get_or_create_node_id(x: float, y: float) -> int:
        nonlocal next_node_id
        # Round to stabilize floating point coordinates used as node keys.
        key = (round(x, 9), round(y, 9))
        if key not in coord_to_node:
            node_id = int(next_node_id)
            coord_to_node[key] = node_id
            G.add_node(node_id, x=x, y=y)
            next_node_id += 1
        return int(coord_to_node[key])

    for row in gdf.itertuples(index=False):
        geom = row.geometry
        coords = list(geom.coords)
        if len(coords) < 2:
            continue

        edge_attrs = row._asdict()
        edge_attrs.pop("geometry", None)

        for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
            u = get_or_create_node_id(float(x1), float(y1))
            v = get_or_create_node_id(float(x2), float(y2))
            if u == v:
                continue

            mx1, my1 = to_metric.transform(x1, y1)
            mx2, my2 = to_metric.transform(x2, y2)
            length = LineString([(mx1, my1), (mx2, my2)]).length

            attrs = {
                **edge_attrs,
                "length": length,
            }
            # Build a bidirectional street graph for routing.
            G.add_edge(u, v, **attrs)
            G.add_edge(v, u, **attrs)

    return G


def add_custom_attributes(G: nx.MultiDiGraph) -> None:
    """
    Add application-specific attributes to graph edges and nodes.

    Added attributes
    ----------------
    Graph:
        ugv_restricted_zones_metric : list of shapely.Polygon
            Polygons drawn by the user to restrict UGV traversal.
    Edge:
        ugv_sidewalk : bool
            True if edge is considered sidewalk-traversable.
    Node:
        ugv_crossing : bool
            True if node is tagged as a crossing.
    """
    # Ensure edge lengths exist (meters)
    ox.distance.add_edge_lengths(G)

    # Initialize graph attribute for user-drawn restricted zones
    if "ugv_restricted_zones_metric" not in G.graph:
        G.graph["ugv_restricted_zones_metric"] = []

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

    # Identify roadway intersections for additional penalty
    for node in G.nodes():
        roadways = [
            (u, v, key)
            for u, v, key, data in G.edges(node, keys=True, data=True)
            if not data.get("ugv_sidewalk")
        ]
        if len(roadways) > 2:
            G.nodes[node]["ugv_intersection"] = True
