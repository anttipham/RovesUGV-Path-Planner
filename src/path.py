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
from shapely.geometry import LineString, Point

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


def connect_to_nearest_edge(
    G: nx.MultiDiGraph,
    node_id: int,
) -> int:
    """
    Split nearest edge (assumed straight) and connect an existing node to it.

    Graph must have node attributes:
        node["x"], node["y"]

    Returns
    -------
    new_node_id (the inserted split node)
    """
    transformer = pyproj.Transformer.from_crs(
        config.MAP_EPSG,
        config.METRIC_EPSG,
        always_xy=True,
    )
    inverse_transformer = pyproj.Transformer.from_crs(
        config.METRIC_EPSG,
        config.MAP_EPSG,
        always_xy=True,
    )

    # Get coordinate from node
    x = G.nodes[node_id]["x"]
    y = G.nodes[node_id]["y"]

    # Project to metric CRS
    proj_x, proj_y = transformer.transform(x, y)
    proj_target_point = Point(proj_x, proj_y)
    proj_graph = ox.project_graph(G, to_crs=config.METRIC_EPSG)

    # Find nearest edge
    u, v, key = ox.distance.nearest_edges(proj_graph, X=proj_x, Y=proj_y)

    # Reconstruct edge line
    proj_ux = proj_graph.nodes[u]["x"]
    proj_uy = proj_graph.nodes[u]["y"]
    proj_vx = proj_graph.nodes[v]["x"]
    proj_vy = proj_graph.nodes[v]["y"]
    edge_line = LineString([(proj_ux, proj_uy), (proj_vx, proj_vy)])

    # Project node onto edge
    projected_distance = edge_line.project(proj_target_point)
    proj_split_point = edge_line.interpolate(projected_distance)
    proj_split_x = float(proj_split_point.x)
    proj_split_y = float(proj_split_point.y)

    # Back to original CRS
    split_x, split_y = inverse_transformer.transform(proj_split_x, proj_split_y)

    # Create split node
    new_node_id = max(G.nodes) + 1
    G.add_node(new_node_id, x=split_x, y=split_y)

    # Remove original edge
    original_attrs = dict(G.edges[u, v, key])
    G.remove_edge(u, v, key)

    # Add split edges
    base_attrs = {k: v for k, v in original_attrs.items() if k != "length"}
    G.add_edge(u, new_node_id, **base_attrs)
    G.add_edge(new_node_id, u, **base_attrs)
    G.add_edge(v, new_node_id, **base_attrs)
    G.add_edge(new_node_id, v, **base_attrs)

    # Connect argument node to split node
    G.add_edge(
        new_node_id,
        node_id,
        foot="yes",
        virtual="yes",
    )
    G.add_edge(
        node_id,
        new_node_id,
        foot="yes",
        virtual="yes",
    )

    return new_node_id


def trim_paths(
    paths: list[list[tuple[int, int]]],
    tolerance: float = 3.0,
) -> list[list[tuple[int, int]]]:
    """
    Trim multiple paths based on their overlap with previously seen coordinates.

    The first path is kept unchanged. For each subsequent path, the function
    finds the last point (iterating from the end) that is within `tolerance`
    (Euclidean distance) of any coordinate already seen in earlier paths.
    The path is then trimmed to start from that point onward.

    All retained segments are accumulated into a shared coordinate list so that
    later paths are compared against all previously accepted points.

    Parameters
    ----------
    paths : list[list[tuple[int, int]]]
        A list of paths, where each path is a list of (x, y) integer coordinates.
        The first path is used as the reference and is not modified.
    tolerance : float, default=3.0
        Maximum Euclidean distance for considering two points as matching.

    Returns
    -------
    list[list[tuple[int, int]]]
        A list of trimmed paths:
        - The first path is unchanged.
        - Each subsequent path contains only the suffix starting from its
          last point that matches (within tolerance) any previously accepted
          coordinate.
        - Paths with no matching point are omitted.
    """
    if len(paths) < 2:
        return paths

    trimmed_paths = [paths[0]]
    coords = paths[0].copy()
    for path in paths[1:]:
        for i in range(len(path) - 1, -1, -1):
            point = path[i]
            # Closest point within tolerance in coords
            min_distance = min(
                np.hypot(point[0] - c[0], point[1] - c[1]) for c in coords
            )
            if min_distance < tolerance:
                trimmed_paths.append(path[i:])
                coords.extend(path[i:])
                break

    return trimmed_paths


def calc_premise_path(G: nx.MultiDiGraph, coord: tuple[float, float]):
    # Download image of the premise area
    x, y = pyproj.Transformer.from_crs(config.MAP_EPSG, config.METRIC_EPSG).transform(
        *coord[::-1]
    )
    bbox = (
        x - config.BBOX_SIZE // 2,
        y - config.BBOX_SIZE // 2,
        x + config.BBOX_SIZE // 2,
        y + config.BBOX_SIZE // 2,
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
    paths = path_image.calc_2d_premise_paths(G, img, bbox, debug_img=True)

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

    # Simplify paths
    simplified_paths = []
    for path in paths.values():
        line = LineString([(y, x) for (x, y) in path])
        simplified = line.simplify(tolerance=2.0)

        # Debug: Show original and simplified paths on the image
        simplified_paths.append([(int(x), int(y)) for y, x in simplified.coords])
        # # print(f"Original path: {path}")
        # print(f"Simplified path: {simplified_points}")
        # draw_comparison(img, path, [(int(y), int(x)) for x, y in simplified_points])
    trim_paths(simplified_paths)

    # Convert pixel locations back to metric coordinates
    metric_paths = [
        [
            (
                bbox[0] + (bbox[2] - bbox[0]) * (x / config.BBOX_IMAGE_SIZE),
                bbox[1] + (bbox[3] - bbox[1]) * (y / config.BBOX_IMAGE_SIZE),
            )
            for x, y in path
        ]
        for path in simplified_paths
    ]

    # Convert back to map CRS
    transformer = pyproj.Transformer.from_crs(
        config.METRIC_EPSG,
        config.MAP_EPSG,
        always_xy=True,
    )
    map_coords: list[list[tuple[float, float]]] = [
        [transformer.transform(x, y) for x, y in path] for path in metric_paths
    ]

    # Make a graph for virtual paths on the premise area
    H = nx.MultiDiGraph()
    # Add the first point as a node
    prev_node_id = max(G.nodes) + 1
    H.add_node(prev_node_id, x=map_coords[0][0], y=map_coords[0][1])
    # Add rest of the paths
    for path in map_coords:
        # First point of the path is already added as a node
        prev_node_id = ox.nearest_nodes(H, path[0][0], path[0][1], return_dist=False)
        for x, y in path[1:]:
            node_id = prev_node_id + 1
            H.add_node(node_id, x=x, y=y)
            H.add_edge(prev_node_id, node_id, foot="yes", virtual="yes")
            H.add_edge(node_id, prev_node_id, foot="yes", virtual="yes")
            prev_node_id = node_id
        # Connect the last point to the nearest edge in the map graph
        G.add_node(node_id, x=x, y=y)
        connect_to_nearest_edge(G, node_id)
    # Update the main graph with the new nodes and edges from the premise paths
    G.update(H)
