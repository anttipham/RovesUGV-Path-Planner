"""
Everything related to algorithms and paths are here
"""

import cv2
import folium
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pyproj
import requests
import shapely
from shapely.geometry import LineString, Point

import config
import osm_gis
import path_image


def update_building_access(G: nx.MultiDiGraph, building_gdf: gpd.GeoDataFrame) -> None:
    # Remove existing temporary connections to the building access nodes
    edges_to_remove = [
        (u, v, k)
        for u, v, k, data in G.edges(keys=True, data=True)
        if data.get("temporary_connection") is True
    ]
    G.remove_edges_from(edges_to_remove)

    # Store existing building access nodes and remove them from the graph
    existing_access_nodes = {
        node: data
        for node, data in G.nodes(data=True)
        if data.get("building_access") is True
    }
    G.remove_nodes_from(existing_access_nodes.keys())

    # Find the nearest point to be used as access way for each building
    access_ways: dict[int, tuple[int, dict]] = {}
    for row in building_gdf.itertuples():
        id = row.Index[1]

        # Find the building node by id
        if id in existing_access_nodes:
            node = existing_access_nodes[id]
        else:
            # If it doesn't exist, add the centroid of a building as a node to the graph
            centroid = shapely.centroid(row.geometry)
            node = {
                "y": centroid.y,
                "x": centroid.x,
                "building_access": True,
            }

        # Attach the centroid to the nearest node excluding the node itself
        nearest_node = ox.distance.nearest_nodes(G, node["x"], node["y"])
        access_ways[id] = (nearest_node, node)

    # Add the access ways to the graph
    for node1, (node2, node_data) in access_ways.items():
        # Add building centroid to graph
        if node1 not in G.nodes():
            G.add_node(node1, **node_data)

        # If the building node is already connected to the graph, skip it
        if G.edges(node1):
            continue
        G.add_edge(node1, node2, foot="yes", temporary_connection=True)
        G.add_edge(node2, node1, foot="yes", temporary_connection=True)


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


def split_nearest_edge(G: nx.MultiDiGraph, x: int, y: int) -> int:
    """
    Split nearest edge (assumed straight).

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

    return new_node_id


def simplify_paths(
    paths: list[list[tuple[int, int]]],
    combination_tolerance: float,
    line_tolerance: float,
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

    # Trim paths
    trimmed_paths = [paths[0]]
    visited_points = list(paths[0])
    for path in paths[1:]:
        for i in range(len(path) - 1, -1, -1):
            point = path[i]
            if any(
                ((point[0] - vp[0]) ** 2 + (point[1] - vp[1]) ** 2) ** 0.5
                <= combination_tolerance
                for vp in visited_points
            ):
                trimmed_paths.append(path[i:])
                visited_points.extend(path[i:])
                break

    # Simplify paths
    simplified_paths = []
    for path in trimmed_paths:
        line = LineString([(x, y) for (x, y) in path])
        simplified = line.simplify(tolerance=line_tolerance)
        simplified_paths.append([(int(x), int(y)) for x, y in simplified.coords])

    return simplified_paths


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

    if not paths:
        return

    # Simplify paths
    simplified_paths = simplify_paths(
        [[(x, y) for y, x in path] for path in paths.values()],
        combination_tolerance=config.SIMPLIFICATION_COMBINATION_TOLERANCE,
        line_tolerance=config.SIMPLIFICATION_LINE_TOLERANCE,
    )

    # Convert pixel locations back to metric coordinates
    metric_paths = [
        [
            (
                bbox[0] + (bbox[2] - bbox[0]) * (x / config.BBOX_IMAGE_SIZE),
                bbox[3] - (bbox[3] - bbox[1]) * (y / config.BBOX_IMAGE_SIZE),
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

    # Add last nodes of the paths as new nodes to the graph
    last_points = [path[-1] for path in map_coords]
    connection_node_ids = []
    for x, y in last_points:
        connection_node_ids.append(split_nearest_edge(G, x, y))

    # Add rest of the paths
    for i, path in enumerate(map_coords):
        # First node of the path
        if i == 0:
            # First node of the first path does not need to be connected to the graph.
            # No need to split an edge.
            node_id = max(G.nodes) + 1
            G.add_node(node_id, x=path[0][0], y=path[0][1])
        else:
            prev_node_id = split_nearest_edge(G, path[0][0], path[0][1])
            node_id = max(G.nodes) + 1
            G.add_node(node_id, x=path[0][0], y=path[0][1])
            G.add_edge(prev_node_id, node_id, foot="yes", virtual="yes")
            G.add_edge(node_id, prev_node_id, foot="yes", virtual="yes")
        prev_node_id = node_id
        node_id = prev_node_id + 1

        # Rest of the nodes in the path
        for x, y in path[1:]:
            G.add_node(node_id, x=x, y=y)
            G.add_edge(prev_node_id, node_id, foot="yes", virtual="yes")
            G.add_edge(node_id, prev_node_id, foot="yes", virtual="yes")
            prev_node_id = node_id
            node_id = prev_node_id + 1
        # Connect the end of the path to the connection node on the road graph
        G.add_edge(prev_node_id, connection_node_ids[i], foot="yes", virtual="yes")
        G.add_edge(connection_node_ids[i], prev_node_id, foot="yes", virtual="yes")
