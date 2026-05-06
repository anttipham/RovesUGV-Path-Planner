"""
Graph routing algorithms and virtual premise path insertion.

Implements turn-aware shortest-path algorithms, building-access node management,
edge centrality computation, and conversion of 2D raster paths to graph edges.
"""

import collections
import heapq
import math
from typing import Callable, Iterable

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
import graph
import path_image

transformer_to_metric = pyproj.Transformer.from_crs(config.MAP_EPSG, config.METRIC_EPSG)


def update_building_access(G: nx.MultiDiGraph) -> None:
    """
    Rebuild temporary building-access connectors in the graph.

    For each building, a building-access node is created (or reused), then connected
    bidirectionally to the nearest graph node via `ugv_closest_node_connection` edges.
    Existing temporary access edges/nodes are removed before regeneration.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Road graph to modify.
    """
    # Remove existing closest node connections to the building access nodes
    edges_to_remove = [
        (u, v, k)
        for u, v, k, data in G.edges(keys=True, data=True)
        if data.get("ugv_closest_node_connection") is True
    ]
    G.remove_edges_from(edges_to_remove)

    # Store existing building access nodes and remove them from the graph
    existing_access_nodes = {
        node: data
        for node, data in G.nodes(data=True)
        if data.get("ugv_building_access") is True
    }
    G.remove_nodes_from(existing_access_nodes.keys())

    # Find the nearest edge to be used as access way for each building
    access_ways: dict[int, tuple[int, dict]] = {}
    building_gdf = G.graph.get("ugv_buildings")
    if building_gdf is None:
        return
    for row in building_gdf.itertuples():
        id = row.id
        print(f"Processing building {id}")

        # Find the building node by id
        if id in existing_access_nodes:
            node = existing_access_nodes[id]
        else:
            # If it doesn't exist, add the centroid of a building as a node to the graph
            centroid = shapely.centroid(row.geometry)
            node = {
                "y": centroid.y,
                "x": centroid.x,
                "ugv_building_access": True,
                "ugv_sidewalk": True,
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
        G.add_edge(node1, node2, ugv_sidewalk=True, ugv_closest_node_connection=True)
        G.add_edge(node2, node1, ugv_sidewalk=True, ugv_closest_node_connection=True)


# def turn_aware_dijkstra(
#     G: nx.MultiDiGraph,
#     source: int,
#     targets: Iterable[int],
#     *,
#     cost: Callable[
#         [tuple[int, int, int] | None, tuple[int, int, int], nx.MultiDiGraph],
#         float,
#     ],
# ) -> tuple[dict[int, float], dict[int, list[tuple[int, int, int]]]]:
#     """
#     Compute shortest paths from one source to many targets with turn costs.

#     This algorithm treats the traversal cost of an edge as potentially dependent
#     on the previously used edge (turn cost). The search state includes both the
#     current node and the incoming edge.

#     Parameters
#     ----------
#     G : nx.MultiDiGraph
#         Directed multigraph.
#     source : int
#         Source node id.
#     targets : Iterable[int]
#         Target node ids.
#     cost : Callable
#         Function computing the cost of traversing `curr_edge` after `prev_edge`.

#         Signature: `cost(prev_edge, curr_edge, G) -> float`

#         - `prev_edge` is None for the first move from source
#         - `curr_edge` is tuple (u, v, key)
#         - Cost must be non-negative

#     Returns
#     -------
#     distances : dict[int, float]
#         Shortest distance to each target. Unreachable: value = infinity.
#     paths : dict[int, list[tuple[int, int, int]]]
#         Edge-based shortest path to each target. Unreachable: value = [].
#     """

#     # Validate
#     if not isinstance(G, nx.MultiDiGraph):
#         raise TypeError("G must be a nx.MultiDiGraph")
#     if source not in G:
#         raise nx.NodeNotFound(f"Source node {source!r} not in graph")

#     targets = set(targets)
#     missing = [t for t in targets if t not in G]
#     if missing:
#         raise nx.NodeNotFound(f"Target nodes not in graph: {missing!r}")

#     # Initial state: current node = source, previous edge = None
#     start_state: tuple[int, tuple[int, int, int] | None] = (source, None)

#     dist: dict[tuple[int, tuple[int, int, int] | None], float] = {start_state: 0.0}
#     parent: dict[
#         tuple[int, tuple[int, int, int] | None],
#         tuple[int, tuple[int, int, int] | None] | None,
#     ] = {start_state: None}
#     used_edge: dict[
#         tuple[int, tuple[int, int, int] | None],
#         tuple[int, int, int] | None,
#     ] = {start_state: None}

#     heap: list[tuple[float, int, tuple[int, tuple[int, int, int] | None]]] = []
#     counter = 0
#     heapq.heappush(heap, (0.0, counter, start_state))

#     best_target_state: dict[int, tuple[int, tuple[int, int, int] | None]] = {}
#     best_target_dist: dict[int, float] = {}
#     remaining = set(targets)

#     while heap and remaining:
#         cur_dist, _, state = heapq.heappop(heap)
#         node, prev_edge = state

#         # Skip stale heap entries
#         if cur_dist != dist.get(state, math.inf):
#             continue

#         # If this state reaches a target, record it as optimal
#         if node in remaining:
#             best_target_state[node] = state
#             best_target_dist[node] = cur_dist
#             remaining.remove(node)

#             if not remaining:
#                 break

#         # Relax all outgoing edges
#         for _, next_node, key in G.out_edges(node, keys=True):
#             curr_edge = (node, next_node, key)
#             step_cost = cost(prev_edge, curr_edge, G)

#             if step_cost < 0:
#                 raise ValueError("Dijkstra requires non-negative costs")

#             new_dist = cur_dist + step_cost
#             next_state = (next_node, curr_edge)

#             if new_dist < dist.get(next_state, math.inf):
#                 dist[next_state] = new_dist
#                 parent[next_state] = state
#                 used_edge[next_state] = curr_edge

#                 counter += 1
#                 heapq.heappush(heap, (new_dist, counter, next_state))

#     # Build results
#     distances: dict[int, float] = {}
#     paths: dict[int, list[tuple[int, int, int]]] = {}

#     for target in targets:
#         if target not in best_target_state:
#             distances[target] = math.inf
#             paths[target] = []
#             continue

#         distances[target] = best_target_dist[target]

#         state = best_target_state[target]
#         edge_path: list[tuple[int, int, int]] = []

#         while state != start_state:
#             edge = used_edge[state]
#             if edge is None:
#                 break
#             edge_path.append(edge)
#             state = parent[state]

#         edge_path.reverse()
#         paths[target] = edge_path

#     return distances, paths


def dijkstra_to_targets_edges(
    G: nx.MultiDiGraph,
    source: int,
    targets: set[int],
    cost_fn: Callable[[nx.MultiDiGraph, tuple[int, int, int]], float],
) -> tuple[dict[int, float], dict[int, list[tuple[int, int, int]]]]:
    """
    Compute shortest edge-based paths from a source to multiple targets.

    Dijkstra's algorithm with early termination once all targets are reached.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Directed multigraph.
    source : int
        Starting node.
    targets : set[int]
        Target node ids.
    cost_fn : Callable
        Function computing edge cost: `cost_fn(G, edge) -> float`

        where `edge = (u, v, key)`.

    Returns
    -------
    distances : dict[int, float]
        Shortest distance to each reachable target.
    edge_paths : dict[int, list[tuple[int, int, int]]]
        Edge-based path [(u, v, key), ...] for each reachable target.

    Raises
    ------
    ValueError
        If source is not in graph or edge cost is negative.
    """

    if source not in G:
        raise ValueError(f"Source node {source!r} is not in the graph.")

    if not targets:
        return {}, {}

    remaining_targets = set(targets)
    distances: dict[int, float] = {source: 0.0}
    predecessor_edge: dict[int, tuple[int, int, int] | None] = {source: None}
    visited: set[int] = set()
    heap: list[tuple[float, int]] = [(0.0, source)]

    while heap and remaining_targets:
        current_dist, u = heapq.heappop(heap)

        if u in visited:
            continue

        visited.add(u)

        if u in remaining_targets:
            remaining_targets.remove(u)

        # Relax all outgoing edges
        for _, v, k in G.out_edges(u, keys=True):
            if v in visited:
                continue

            edge = (u, v, k)
            edge_cost = cost_fn(G, edge)

            if edge_cost == math.inf:
                continue

            if edge_cost < 0:
                raise ValueError(
                    f"Dijkstra requires non-negative edge costs, got {edge_cost} for edge {edge}."
                )

            new_dist = current_dist + edge_cost

            if new_dist < distances.get(v, math.inf):
                distances[v] = new_dist
                predecessor_edge[v] = edge
                heapq.heappush(heap, (new_dist, v))

    # Reconstruct paths
    reachable_distances: dict[int, float] = {}
    reachable_edge_paths: dict[int, list[tuple[int, int, int]]] = {}

    for target in targets:
        if target not in distances:
            continue

        path_edges: list[tuple[int, int, int]] = []
        node = target

        while node != source:
            edge = predecessor_edge[node]

            if edge is None:
                break

            path_edges.append(edge)
            node = edge[0]

        path_edges.reverse()

        reachable_distances[target] = distances[target]
        reachable_edge_paths[target] = path_edges

    return reachable_distances, reachable_edge_paths


def calculate_cost(G: nx.MultiDiGraph, curr_edge: tuple[int, int, int]) -> float:
    """
    Calculate the routing cost of traversing an edge in the graph.

    Includes base traversal cost, crossing penalties, and centrality factor.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph with edge and node attributes.
    curr_edge : tuple[int, int, int]
        Edge as (u, v, key).

    Returns
    -------
    float
        Non-negative traversal cost.

    Notes
    -----
    Cost components:
    - Base: COST_SIDEWALK * length (meters)
    - Roadway penalty: COST_ROADWAY * length
    - Crossing penalties vary by type (traffic signals, zebra, etc.)
    - Roadway crossing exit penalty: COST_ROADWAY_CROSSING
    - Centrality factor: scaled by 1 - (centrality / max_centrality)
    """
    prev_node, curr_node, key = curr_edge

    # Skip edges intersecting with the restricted zones
    # Metric CRS is used for accurate intersection checks
    edge_geom_metric = LineString(
        [
            transformer_to_metric.transform(
                G.nodes[prev_node]["y"], G.nodes[prev_node]["x"]
            ),
            transformer_to_metric.transform(
                G.nodes[curr_node]["y"], G.nodes[curr_node]["x"]
            ),
        ]
    )

    if any(
        edge_geom_metric.intersects(zone)
        for zone in G.graph.get("ugv_restricted_zones_metric", [])
    ):
        return math.inf

    # Warning
    if "ugv_sidewalk" not in G.edges[curr_edge]:
        print(
            f"Warning: edge {G.edges[curr_edge]} between {G.nodes[curr_edge[0]]} "
            f"and {G.nodes[curr_edge[1]]} is missing 'ugv_sidewalk' attribute"
        )

    # Add base cost for the edge
    length = G.edges[curr_edge]["length"]
    penalty = config.COST_SIDEWALK * length

    # Add penalty for crossings
    if G.nodes[curr_node].get("ugv_crossing"):
        match G.nodes[curr_node].get("crossing"):
            case "traffic_signals":
                penalty += config.COST_TRAFFIC_SIGNALS
            case "zebra" | "marked" | "uncontrolled":
                penalty += config.COST_ZEBRA_CROSSING
            case _:
                penalty += config.COST_UNCONTROLLED_CROSSING

    # Extra penalty for using roadway intersections on roadways
    if not G.edges[curr_edge].get("ugv_sidewalk") and G.nodes[prev_node].get(
        "ugv_intersection"
    ):
        penalty += config.COST_ROADWAY_CROSSING

    # Penalty for roadways
    if not G.edges[curr_edge].get("ugv_sidewalk"):
        penalty += config.COST_ROADWAY * length

    # Penalty for not following high centrality paths
    if "ugv_centrality" in G.edges[curr_edge]:
        penalty += (
            config.COST_CENTRALITY_FACTOR
            * length
            * (1 - G.edges[curr_edge]["ugv_centrality"] / G.graph["ugv_max_centrality"])
        )
    else:
        penalty += config.COST_CENTRALITY_FACTOR * length

    return penalty


def add_all_building_path_pairs(G: nx.MultiDiGraph) -> None:
    """
    Compute shortest edge paths between all building-access node pairs.

    Uses Dijkstra's algorithm with custom cost function. Results are stored
    in the graph's `all_building_path_pairs` attribute.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph with building-access nodes (ugv_building_access=True).

    Notes
    -----
    Sets graph attribute:
        G.graph["ugv_all_building_path_pairs"][(source, target)] = [(u, v, key), ...]
    """
    chosen_buildings = set(
        node
        for node, is_ugv_building_access in G.nodes(data="ugv_building_access")
        if is_ugv_building_access
    )

    all_building_path_pairs: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for source in chosen_buildings:
        distances, paths = dijkstra_to_targets_edges(
            G, source, chosen_buildings, calculate_cost
        )
        edge_paths = {(source, target): path for target, path in paths.items()}
        all_building_path_pairs.update(edge_paths)

    G.graph["ugv_all_building_path_pairs"] = all_building_path_pairs


def add_betweenness_centrality(G: nx.MultiDiGraph) -> None:
    """
    Count how often each edge appears in building-to-building shortest paths.

    Stores edge frequencies and maximum centrality in graph attributes for
    route preference during pathfinding.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph with precomputed all_building_path_pairs attribute.

    Notes
    -----
    Sets:
    - Edge attribute: `ugv_centrality` (frequency count)
    - Graph attribute: `ugv_max_centrality` (max frequency)
    """
    all_building_path_pairs: dict[tuple[int, int], list[tuple[int, int, int]]] = (
        G.graph["ugv_all_building_path_pairs"]
    )
    centralities = collections.Counter(
        edge for path in all_building_path_pairs.values() for edge in path
    )

    G.graph["ugv_max_centrality"] = max(centralities.values()) if centralities else 0

    for edge in G.edges(keys=True):
        G.edges[edge]["ugv_centrality"] = centralities.get(edge, 0)


def split_nearest_edge(G: nx.MultiDiGraph, x: float, y: float) -> int:
    """
    Insert a new node by splitting the nearest edge to map coordinate (x, y).

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph to modify.
    x, y : float
        Longitude/latitude in map CRS (config.MAP_EPSG).

    Returns
    -------
    int
        Node id of the inserted split node.
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
    Trim and simplify multiple paths based on overlap with previous coordinates.

    The first path is kept unchanged. For each subsequent path, the function
    finds the last point (iterating from the end) that is within `tolerance`
    (Euclidean distance) of any coordinate already seen in earlier paths.
    The path is then trimmed to start from that point onward.

    All retained segments are accumulated into a shared coordinate list so that
    later paths are compared against all previously accepted points.

    Parameters
    ----------
    paths : list[list[tuple[int, int]]]
        List of paths, where each path is a list of (x, y) integer coordinates.
    combination_tolerance : float
        Maximum Euclidean distance for considering two points as matching.
    line_tolerance : float
        Tolerance parameter for LineString.simplify() operation.

    Returns
    -------
    list[list[tuple[int, int]]]
        Trimmed and simplified paths.
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


def calc_premise_path(G: nx.MultiDiGraph, coord: tuple[float, float]) -> None:
    """
    Add a virtual node at the clicked map point and connect it to the nearest edge.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph to modify in-place.
    coord : tuple[float, float]
        Map coordinate (lon, lat) in config.MAP_EPSG.
    """
    # Add a node exactly at the clicked coordinate and connect it to the nearest edge.
    clicked_node_id = max(G.nodes) + 1
    G.add_node(
        clicked_node_id,
        x=coord[0],
        y=coord[1],
    )

    clicked_connection_node_id = split_nearest_edge(G, coord[0], coord[1])
    G.add_edge(
        clicked_node_id,
        clicked_connection_node_id,
        ugv_sidewalk=True,
        ugv_virtual="yes",
    )
    G.add_edge(
        clicked_connection_node_id,
        clicked_node_id,
        ugv_sidewalk=True,
        ugv_virtual="yes",
    )
