"""
Everything related to algorithms and paths are here
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
import osm_gis
import path_image


def update_building_access(G: nx.MultiDiGraph, building_gdf: gpd.GeoDataFrame) -> None:
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
                "ugv_building_access": True,
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


def turn_aware_dijkstra(
    G: nx.MultiDiGraph,
    source: int,
    targets: Iterable[int],
    *,
    cost: Callable[
        [tuple[int, int, int] | None, tuple[int, int, int], nx.MultiDiGraph],
        float,
    ],
) -> tuple[dict[int, float], dict[int, list[tuple[int, int, int]]]]:
    """
    Compute shortest paths from one source to many targets in a MultiDiGraph,
    where the traversal cost of an edge may depend on the previously used edge.

    Each search state is:
        (current_node, incoming_edge)

    This is necessary for turn-aware routing, because arriving at the same node
    through different incoming edges can lead to different onward costs.

    Parameters
    ----------
    G
        Directed multigraph.
    source
        Source node id.
    targets
        Target node ids.
    cost
        Function that returns the full traversal cost of taking curr_edge after
        prev_edge.

            cost(prev_edge, curr_edge, G) -> non-negative float

        - prev_edge is None for the first move from the source
        - curr_edge is (u, v, key)

    Returns
    -------
    distances, paths
        distances[target] = shortest distance from source to target
        paths[target] = shortest edge path as a list of (u, v, key)

        Unreachable targets get:
            distance = math.inf
            path = []
    """

    # Validate
    if not isinstance(G, nx.MultiDiGraph):
        raise TypeError("G must be a nx.MultiDiGraph")
    if source not in G:
        raise nx.NodeNotFound(f"Source node {source!r} not in graph")

    targets = set(targets)
    missing = [t for t in targets if t not in G]
    if missing:
        raise nx.NodeNotFound(f"Target nodes not in graph: {missing!r}")

    # Initial state:
    # - current node = source
    # - previous edge = None, because no edge has been taken yet
    start_state: tuple[int, tuple[int, int, int] | None] = (source, None)

    # Shortest known distance to each expanded state.
    # Key = (node, incoming_edge)
    dist: dict[tuple[int, tuple[int, int, int] | None], float] = {start_state: 0.0}

    # Parent pointer for path reconstruction:
    # parent[next_state] = previous_state
    parent: dict[
        tuple[int, tuple[int, int, int] | None],
        tuple[int, tuple[int, int, int] | None] | None,
    ] = {start_state: None}

    # Edge used to enter each state.
    # For start_state, there is no entering edge.
    used_edge: dict[
        tuple[int, tuple[int, int, int] | None],
        tuple[int, int, int] | None,
    ] = {start_state: None}

    # Priority queue entries are:
    #   (best_distance_so_far, tie_breaker, state)
    #
    # The tie_breaker avoids Python needing to compare the state tuples when
    # two distances are equal.
    heap: list[tuple[float, int, tuple[int, tuple[int, int, int] | None]]] = []
    counter = 0
    heapq.heappush(heap, (0.0, counter, start_state))

    # For each target node, store the first state popped from the heap.
    # In Dijkstra, the first popped state is optimal.
    best_target_state: dict[int, tuple[int, tuple[int, int, int] | None]] = {}

    # Store the optimal distance for each target node.
    best_target_dist: dict[int, float] = {}

    # Targets still not finalized.
    # Once all are found, we can stop early.
    remaining = set(targets)

    # Main Dijkstra loop.
    while heap and remaining:
        cur_dist, _, state = heapq.heappop(heap)
        node, prev_edge = state

        # Skip stale heap entries.
        # This happens when a better distance to the same state was pushed later.
        if cur_dist != dist.get(state, math.inf):
            continue

        # If this popped state reaches a target node, it is the optimal arrival
        # for that target, so record it.
        if node in remaining:
            best_target_state[node] = state
            best_target_dist[node] = cur_dist
            remaining.remove(node)

            # Early exit: all requested targets have been finalized.
            if not remaining:
                break

        # Relax all outgoing edges from the current node.
        for _, next_node, key in G.out_edges(node, keys=True):
            # Current candidate edge to traverse.
            curr_edge = (node, next_node, key)

            # Full step cost includes both edge cost and any turn cost.
            step_cost = cost(prev_edge, curr_edge, G)

            # Dijkstra requires non-negative costs.
            if step_cost < 0:
                raise ValueError("Dijkstra requires non-negative costs")

            # Total distance if we take this edge.
            new_dist = cur_dist + step_cost

            # New state after traversing curr_edge:
            # we arrive at nbr, and curr_edge becomes the previous edge.
            next_state = (next_node, curr_edge)

            # Standard Dijkstra relaxation.
            if new_dist < dist.get(next_state, math.inf):
                dist[next_state] = new_dist
                parent[next_state] = state
                used_edge[next_state] = curr_edge

                # Push improved state to heap.
                counter += 1
                heapq.heappush(heap, (new_dist, counter, next_state))

    # Final outputs keyed only by target node.
    distances: dict[int, float] = {}
    paths: dict[int, list[tuple[int, int, int]]] = {}

    # Build result for each requested target.
    for target in targets:
        # Unreachable target.
        if target not in best_target_state:
            distances[target] = math.inf
            paths[target] = []
            continue

        # Optimal distance to target.
        distances[target] = best_target_dist[target]

        # Reconstruct optimal edge path by walking parent pointers backward
        # from the best final state.
        state = best_target_state[target]
        edge_path: list[tuple[int, int, int]] = []

        while state != start_state:
            edge = used_edge[state]
            if edge is None:
                break
            edge_path.append(edge)
            state = parent[state]

        # Reconstruction was backward, so reverse it.
        edge_path.reverse()
        paths[target] = edge_path

    return distances, paths


def dijkstra_to_targets_edges(
    G: nx.MultiDiGraph,
    source: int,
    targets: set[int],
    cost_fn: Callable[[nx.MultiDiGraph, tuple[int, int, int]], float],
) -> tuple[dict[int, float], dict[int, list[tuple[int, int, int]]]]:
    """
    Compute shortest paths from a source node to a set of target nodes
    using Dijkstra's algorithm.

    Key features:
    - Works with MultiDiGraph (handles parallel edges via keys)
    - Uses a custom edge cost function
    - Stops early once all targets are reached (performance optimization)
    - Returns edge-based paths instead of node-only paths

    Args:
        G: Directed multigraph
        source: Starting node
        targets: Set of target nodes we want shortest paths to
        cost_fn: Function to compute edge cost

    Returns:
        distances:
            dict[target] -> shortest distance from source

        edge_paths:
            dict[target] -> list of edges (u, v, k) forming the shortest path

        Note:
            Only reachable targets are included in the output.
    """

    # --- Input validation ---
    if source not in G:
        raise ValueError(f"Source node {source!r} is not in the graph.")

    # If no targets, nothing to compute
    if not targets:
        return {}, {}

    # Track which targets we still need to find
    remaining_targets = set(targets)

    # Distance from source to each node (initialized with source = 0)
    distances: dict[int, float] = {source: 0.0}

    # For each node, store the edge used to reach it
    # This allows reconstructing the path later
    predecessor_edge: dict[int, tuple[int, int, int] | None] = {source: None}

    # Track finalized nodes (standard Dijkstra "visited" set)
    visited: set[int] = set()

    # Priority queue storing (distance, node)
    heap: list[tuple[float, int]] = [(0.0, source)]

    # --- Main Dijkstra loop ---
    while heap and remaining_targets:
        # Get node with smallest known distance
        current_dist, u = heapq.heappop(heap)

        # Skip if already processed (lazy deletion from heap)
        if u in visited:
            continue

        # Mark node as finalized
        visited.add(u)

        # If this node is one of our targets, mark it as found
        if u in remaining_targets:
            remaining_targets.remove(u)

        # Relax all outgoing edges from u
        for _, v, k in G.out_edges(u, keys=True):
            # Skip already finalized nodes
            if v in visited:
                continue

            edge = (u, v, k)

            # Compute edge cost using user-provided function
            edge_cost = cost_fn(G, edge)

            # Dijkstra requires non-negative weights
            if edge_cost < 0:
                raise ValueError(
                    f"Dijkstra requires non-negative edge costs, got {edge_cost} for edge {edge}."
                )

            # Compute new candidate distance
            new_dist = current_dist + edge_cost

            # If we found a better path to v, update it
            if new_dist < distances.get(v, math.inf):
                distances[v] = new_dist

                # Store the edge used to reach v
                predecessor_edge[v] = edge

                # Push updated distance to heap
                heapq.heappush(heap, (new_dist, v))

    # --- Reconstruct paths for reachable targets ---
    reachable_distances: dict[int, float] = {}
    reachable_edge_paths: dict[int, list[tuple[int, int, int]]] = {}

    for target in targets:
        # Skip unreachable targets
        if target not in distances:
            continue

        path_edges: list[tuple[int, int, int]] = []
        node = target

        # Backtrack from target to source using predecessor edges
        while node != source:
            edge = predecessor_edge[node]

            # Safety check (should not happen for reachable nodes)
            if edge is None:
                break

            path_edges.append(edge)

            # Move to previous node (u of edge u->v)
            node = edge[0]

        # Reverse to get source -> target order
        path_edges.reverse()

        reachable_distances[target] = distances[target]
        reachable_edge_paths[target] = path_edges

    return reachable_distances, reachable_edge_paths


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


def calculate_cost(G: nx.MultiDiGraph, curr_edge: tuple[int, int, int]) -> float:
    """
    Calculate the cost of traversing an edge in the graph.

    Args:
        G: The graph.
        edge: A tuple (u, v, key) representing the edge to calculate the cost for.

    Returns:
        The weight of the edge.
    """
    prev_node, curr_node, key = curr_edge

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

    # Extra penalty for leaving crossings on roadways
    if not G.edges[curr_edge].get("ugv_sidewalk") and G.nodes[prev_node].get(
        "ugv_crossing"
    ):
        penalty += config.COST_ROADWAY_CROSSING

    # Penalty for roadways
    if not G.edges[curr_edge].get("ugv_sidewalk"):
        penalty += config.COST_ROADWAY * length

    # Penalty for not following high centrality paths
    if "centrality" in G.edges[curr_edge]:
        penalty += (
            config.COST_CENTRALITY_FACTOR
            * length
            * (1 - G.edges[curr_edge]["centrality"] / G.graph["max_centrality"])
        )
    else:
        penalty += config.COST_CENTRALITY_FACTOR * length

    return penalty


def add_all_building_path_pairs(G: nx.MultiDiGraph) -> None:
    # Building node IDs
    chosen_buildings = set(
        node
        for node, is_ugv_building_access in G.nodes(data="ugv_building_access")
        if is_ugv_building_access
    )

    all_building_path_pairs: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for source in chosen_buildings:
        # node_paths = nx.single_source_dijkstra_path(
        #     G,
        #     source,
        #     weight=lambda u, v, _: calculate_cost(G, u, v),
        # )
        # edge_paths = {
        #     (source, target): [
        #         (u, v, next(iter(G[u][v])))
        #         for u, v in zip(node_path[:-1], node_path[1:])
        #     ]
        #     for target, node_path in node_paths.items()
        #     if target in chosen_buildings
        # }
        distances, paths = dijkstra_to_targets_edges(
            G, source, chosen_buildings, calculate_cost
        )
        edge_paths = {(source, target): path for target, path in paths.items()}
        all_building_path_pairs.update(edge_paths)

    G.graph["all_building_path_pairs"] = all_building_path_pairs


def add_betweenness_centrality(G: nx.MultiDiGraph) -> None:
    all_building_path_pairs: dict[tuple[int, int], list[tuple[int, int, int]]] = (
        G.graph["all_building_path_pairs"]
    )
    centralities = collections.Counter(
        edge for path in all_building_path_pairs.values() for edge in path
    )

    G.graph["max_centrality"] = max(centralities.values())

    for edge in G.edges(keys=True):
        G.edges[edge]["centrality"] = centralities.get(edge, 0)


# def calc_path(
#     G: nx.MultiDiGraph,
#     source: int | None,
#     target: int | None,
# ) -> list[tuple[int, int, int]]:
#     if None in (source, target):
#         return []

#     shortest_node_path = ox.shortest_path(G, source, target, weight="weight")
#     # Calculate the correct key of MultiDiGraph
#     shortest_edge_path: list[tuple[int, int, int]] = []
#     for u, v in zip(shortest_node_path[:-1], shortest_node_path[1:]):
#         # Find the minimum-weight edge between u and v
#         min_data = (float("inf"), 0)
#         for key, value in G[u][v].items():
#             min_data = min(min_data, (value["weight"], key))
#         shortest_edge_path.append((u, v, min_data[1]))

#     return shortest_edge_path


def show_path(
    G: nx.MultiDiGraph,
) -> folium.FeatureGroup:
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
    edges = G.graph["all_building_path_pairs"].get((ids[0], ids[1]), [])
    path_graph = G.edge_subgraph(edges)
    folium.GeoJson(
        ox.graph_to_gdfs(path_graph, nodes=False),
        style_function=lambda _: {
            "color": "#007AD1",
            "weight": 4,
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
            G.add_edge(prev_node_id, node_id, ugv_sidewalk=True, ugv_virtual="yes")
            G.add_edge(node_id, prev_node_id, ugv_sidewalk=True, ugv_virtual="yes")
        prev_node_id = node_id
        node_id = prev_node_id + 1

        # Rest of the nodes in the path
        for x, y in path[1:]:
            G.add_node(node_id, x=x, y=y)
            G.add_edge(prev_node_id, node_id, ugv_sidewalk=True, ugv_virtual="yes")
            G.add_edge(node_id, prev_node_id, ugv_sidewalk=True, ugv_virtual="yes")
            prev_node_id = node_id
            node_id = prev_node_id + 1
        # Connect the end of the path to the connection node on the road graph
        G.add_edge(
            prev_node_id, connection_node_ids[i], ugv_sidewalk=True, ugv_virtual="yes"
        )
        G.add_edge(
            connection_node_ids[i], prev_node_id, ugv_sidewalk=True, ugv_virtual="yes"
        )
