"""
Everything related to algorithms and paths are here
"""

import cv2
import folium
import networkx as nx
import numpy as np
import osmnx as ox
import pyproj
import requests
from shapely.geometry import LineString

import config
import osm_gis
import path_image


def add_weight(G: nx.MultiDiGraph) -> None:
    """
    TODO: Add weight for junctions
    """
    edge: dict
    for edge in G.edges.values():
        edge["weight"] = edge["length"]
        # Add more weight if the path is not for pedestrians
        if edge.get("foot") not in ("yes", "designated"):
            edge["weight"] *= 3


def add_centrality(G: nx.MultiDiGraph) -> None:
    # Calculate centrality for only buildings
    buildings = [
        node
        for node, is_building_access in G.nodes(data="building_access")
        if is_building_access
    ]
    centrality = nx.edge_betweenness_centrality_subset(
        G,
        sources=buildings,
        targets=buildings,
        weight="weight",
    )
    for key, edge in G.edges.items():
        edge["centrality"] = centrality[key]


def get_chosen_building_nodes(G: nx.MultiDiGraph) -> list[int]:
    # Find all chosen buildings
    all_chosen_buildings = [
        (chosen_time, node)
        for node, chosen_time in G.nodes(data="chosen_time")
        if chosen_time
    ]
    all_chosen_buildings.sort()
    chosen_buildings = [node for _, node in all_chosen_buildings[-2:]]
    return chosen_buildings


def calc_path(
    G: nx.MultiDiGraph,
    source: int | None,
    target: int | None,
) -> list[tuple[int, int, int]]:
    if None in (source, target):
        return []

    shortest_node_path = ox.shortest_path(G, source, target, weight="weight")
    # Calculate the correct key of MultiDiGraph
    shortest_edge_path: list[tuple[int, int, int]] = []
    for u, v in zip(shortest_node_path[:-1], shortest_node_path[1:]):
        # Find the minimum-weight edge between u and v
        min_data = (float("inf"), 0)
        for key, value in G[u][v].items():
            min_data = min(min_data, (value["weight"], key))
        shortest_edge_path.append((u, v, min_data[1]))

    return shortest_edge_path


def show_path(G: nx.MultiDiGraph) -> folium.FeatureGroup:
    fg = folium.FeatureGroup(name=config.PATH_LAYER_NAME)
    ids = get_chosen_building_nodes(G)

    # Show chosen buildings
    buildings = osm_gis.get_building_gdf()
    chosen_buildings = buildings[buildings.index.get_level_values("id").isin(ids)]
    folium.GeoJson(
        chosen_buildings,
        style_function=lambda _: {
            "fillColor": "red",
            "color": "black",
            "weight": 3,
            "fillOpacity": 0.5,
        },
    ).add_to(fg)

    # Path requires a (1) source and (2) target node
    if len(ids) < 2:
        return fg

    # Show shortest path between buildings
    edges = calc_path(G, ids[0], ids[1])
    path_graph = G.edge_subgraph(edges)
    folium.GeoJson(
        ox.graph_to_gdfs(path_graph, nodes=False),
        style_function=lambda _: {
            "color": "red",
            "weight": 3,
            "opacity": 1,
        },
    ).add_to(fg)

    return fg


def calc_premise_path(G: nx.MultiDiGraph, coord: tuple[float, float]):
    # Download image of the premise area
    x, y = pyproj.Transformer.from_crs(config.MAP_EPSG, config.METRIC_EPSG).transform(
        *coord[::-1]
    )
    bbox = (
        x - config.BBOX_SIZE,
        y - config.BBOX_SIZE,
        x + config.BBOX_SIZE,
        y + config.BBOX_SIZE,
    )
    # print(f"Calculating premise bbox: {x-500},{y-500},{x+500},{y+500}")
    url = "http://localhost:8080/service"
    params = {
        "service": "WMS",
        "request": "GetMap",
        "layers": "seinajoki_topographic_image",
        "styles": "",
        "format": "image/png",
        "transparent": "true",
        "version": "1.1.1",
        "width": config.BBOX_IMAGE_SIZE,
        "height": config.BBOX_IMAGE_SIZE,
        "srs": config.METRIC_EPSG,
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
    }
    response = requests.get(url, params=params)
    img_array = np.frombuffer(response.content, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)

    # Compute paths on the premise image and add them to the map
    paths = path_image.calc_2d_premise_paths(G, img, bbox)

    # def draw_comparison(
    #     image: np.ndarray,
    #     original_points: list[tuple[int, int]],
    #     simplified_points: list[tuple[int, int]],
    # ) -> None:
    #     if image.ndim == 2:
    #         vis = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    #     else:
    #         vis = image.copy()
    #     # Original (thin yellow)
    #     for y, x in original_points:
    #         cv2.circle(vis, (x, y), 1, (0, 255, 255), -1)
    #     # Simplified (larger red)
    #     cv2.polylines(vis, [np.array(simplified_points)], False, (0, 0, 255), 2)
    #     # for y, x in simplified_points:
    #     #     cv2.circle(vis, (x, y), 4, (0, 0, 255), -1)
    #     cv2.imshow("Path Comparison", vis)
    #     cv2.waitKey(0)

    for path in paths.values():
        line = LineString([(y, x) for (x, y) in path])
        simplified = line.simplify(tolerance=2.0)
        simplified_points = [(int(y), int(x)) for y, x in simplified.coords]
        # print(f"Original path: {path}")
        # print(f"Simplified path: {simplified_points}")

        # draw_comparison(img, path, simplified_points)
