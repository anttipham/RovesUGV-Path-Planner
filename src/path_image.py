"""
Warning: This file is largely vibe coded, but the code has been checked.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple

import cv2
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import box

import config

BoundingBox = Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)
Point = Tuple[int, int]  # (row, col)


def build_traversable_mask(
    map_img: np.ndarray,
    threshold: int = 127,
    free_is_dark: bool = True,
    erode_obstacles: int = 0,
) -> np.ndarray:
    """
    Convert a grayscale/RGB map image to a boolean traversable mask.

    Parameters
    ----------
    map_img : np.ndarray
        Input image, grayscale or RGB.
    threshold : int
        Threshold for binarization.
    free_is_dark : bool
        If True, darker pixels are treated as free space.
        If False, brighter pixels are treated as free space.
    erode_obstacles : int
        Optional dilation of obstacles for safety margin.

    Returns
    -------
    traversable : np.ndarray of bool
        True where motion is allowed.
    """
    if map_img.ndim == 3:
        gray = cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = map_img.copy()

    if free_is_dark:
        traversable = gray < threshold
    else:
        traversable = gray > threshold

    traversable = traversable.astype(np.uint8)

    if erode_obstacles > 0:
        # Dilate obstacles => shrink traversable space
        obstacle = 1 - traversable
        kernel = np.ones((erode_obstacles, erode_obstacles), np.uint8)
        obstacle = cv2.dilate(obstacle, kernel, iterations=1)
        traversable = 1 - obstacle

    return traversable.astype(bool)


def compute_obstacle_cost_map(traversable: np.ndarray, max_distance) -> np.ndarray:
    """
    Compute a soft obstacle penalty map using exact pixel rings around obstacles.

    Cost rules for max_distance=5:
        1 pixel from obstacle -> +4
        2 pixels from obstacle -> +3
        3 pixels from obstacle -> +2
        4 pixels from obstacle -> +1
        5 pixels or farther -> +0

    This version uses repeated dilation of the obstacle mask, which gives stable,
    intuitive rings and avoids distance-transform bucketing issues.
    """
    obstacle_mask = (~traversable).astype(np.uint8)
    obstacle_cost_map = np.zeros(traversable.shape, dtype=np.float32)

    # Track already-assigned free cells so each cell only gets the strongest penalty once.
    assigned_mask = obstacle_mask.copy()

    kernel = np.ones((3, 3), dtype=np.uint8)

    for distance in range(1, max_distance):
        dilated_obstacle_mask = cv2.dilate(obstacle_mask, kernel, iterations=distance)

        current_ring_mask = (
            (dilated_obstacle_mask > 0) & (assigned_mask == 0) & traversable
        )
        penalty = float(max_distance - distance)  # 4, 3, 2, 1

        obstacle_cost_map[current_ring_mask] = penalty
        assigned_mask[current_ring_mask] = 1

    return obstacle_cost_map


def find_center_free_cell(traversable: np.ndarray) -> Point:
    """
    Find a free start cell near the image center.
    """
    h, w = traversable.shape
    center = (h // 2, w // 2)

    if traversable[center]:
        return center

    for radius in range(1, max(h, w)):
        r0 = max(0, center[0] - radius)
        r1 = min(h, center[0] + radius + 1)
        c0 = max(0, center[1] - radius)
        c1 = min(w, center[1] + radius + 1)

        candidates = []
        for c in range(c0, c1):
            candidates.append((r0, c))
            candidates.append((r1 - 1, c))
        for r in range(r0 + 1, r1 - 1):
            candidates.append((r, c0))
            candidates.append((r, c1 - 1))

        for p in candidates:
            if traversable[p]:
                return p

    return center  # Fallback, should not happen if there's any free cell at all


def extract_goal_points(goal_mask: np.ndarray) -> List[Point]:
    """
    Convert a binary goal mask into a list of goal cells.
    Nonzero pixels are goals.
    """
    if goal_mask.ndim == 3:
        goal_mask = cv2.cvtColor(goal_mask, cv2.COLOR_BGR2GRAY)

    ys, xs = np.nonzero(goal_mask > 0)
    return list(zip(ys.tolist(), xs.tolist()))


def dijkstra_to_multiple_goals(
    traversable: np.ndarray,
    start: Point,
    goal_points: List[Point],
    return_all_paths: bool = True,
    goal_block_diameter: int = 75,
    obstacle_cost_map: Optional[np.ndarray] = None,
) -> Dict[Point, List[Point]]:
    """
    Run Dijkstra from one start to multiple goal cells.

    When a goal is reached, a filled circle is written into the traversable mask
    as blocked space so nearby goals cannot also be reached.

    Parameters
    ----------
    traversable : np.ndarray
        Boolean traversability mask.
    start : Point
        Start cell.
    goal_points : list[Point]
        Goal cells.
    return_all_paths : bool
        If False, stop after the first reachable goal.
    goal_block_diameter : int
        Diameter of the blocking circle drawn around each reached goal.
    obstacle_cost_map : Optional[np.ndarray]
        Extra per-cell movement penalty for being near obstacles.
    """
    height, width = traversable.shape

    traversable_mask = traversable.copy().astype(bool)

    if obstacle_cost_map is not None and obstacle_cost_map.shape != traversable.shape:
        raise ValueError("obstacle_cost_map must have the same shape as traversable.")

    if not traversable_mask[start]:
        raise ValueError("Start is not traversable.")

    remaining_goals = {
        goal
        for goal in goal_points
        if 0 <= goal[0] < height and 0 <= goal[1] < width and traversable_mask[goal]
    }

    if not remaining_goals:
        return {}

    movement_options = [
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, 2**0.5),
        (-1, 1, 2**0.5),
        (1, -1, 2**0.5),
        (1, 1, 2**0.5),
        (-2, -1, 5**0.5),
        (-2, 1, 5**0.5),
        (2, -1, 5**0.5),
        (2, 1, 5**0.5),
        (-1, -2, 5**0.5),
        (-1, 2, 5**0.5),
        (1, -2, 5**0.5),
        (1, 2, 5**0.5),
    ]

    distance_map: Dict[Point, float] = {start: 0.0}
    parent_map: Dict[Point, Optional[Point]] = {start: None}
    priority_queue: List[Tuple[float, Point]] = [(0.0, start)]
    reached_goal_paths: Dict[Point, List[Point]] = {}

    goal_block_radius = goal_block_diameter // 2

    def reconstruct_path(goal_node: Point) -> List[Point]:
        path: List[Point] = []
        current_node: Optional[Point] = goal_node

        while current_node is not None:
            path.append(current_node)
            current_node = parent_map[current_node]

        path.reverse()
        return path

    def block_goal_region(goal_node: Point) -> None:
        goal_y, goal_x = goal_node

        blocked_mask_uint8 = traversable_mask.astype(np.uint8)
        cv2.circle(
            blocked_mask_uint8,
            (goal_x, goal_y),
            goal_block_radius,
            0,
            thickness=-1,
        )

        traversable_mask[:, :] = blocked_mask_uint8.astype(bool)

    while priority_queue and remaining_goals:
        current_cost, current_node = heapq.heappop(priority_queue)

        if current_node not in distance_map:
            continue
        if current_cost > distance_map[current_node]:
            continue

        current_y, current_x = current_node

        if not traversable_mask[current_y, current_x]:
            continue

        if current_node in remaining_goals:
            reached_goal_paths[current_node] = reconstruct_path(current_node)

            block_goal_region(current_node)

            updated_remaining_goals = set()
            for goal_y, goal_x in remaining_goals:
                if traversable_mask[goal_y, goal_x]:
                    updated_remaining_goals.add((goal_y, goal_x))
            remaining_goals = updated_remaining_goals

            if not return_all_paths:
                break

            continue

        for delta_y, delta_x, move_cost in movement_options:
            neighbor_y = current_y + delta_y
            neighbor_x = current_x + delta_x

            if not (0 <= neighbor_y < height and 0 <= neighbor_x < width):
                continue

            if not traversable_mask[neighbor_y, neighbor_x]:
                continue

            # Prevent diagonal corner cutting
            if abs(delta_y) == 1 and abs(delta_x) == 1:
                if (
                    not traversable_mask[current_y + delta_y, current_x]
                    or not traversable_mask[current_y, current_x + delta_x]
                ):
                    continue

            # Prevent long jump through obstacles
            if (abs(delta_y), abs(delta_x)) in {(2, 1), (1, 2)}:
                step_y = 1 if delta_y > 0 else -1
                step_x = 1 if delta_x > 0 else -1

                if abs(delta_y) == 2:
                    intermediate_cells = [
                        (current_y + step_y, current_x),
                        (current_y + step_y, current_x + step_x),
                        (current_y + 2 * step_y, current_x),
                    ]
                else:
                    intermediate_cells = [
                        (current_y, current_x + step_x),
                        (current_y + step_y, current_x + step_x),
                        (current_y, current_x + 2 * step_x),
                    ]

                move_blocked = False
                for check_y, check_x in intermediate_cells:
                    if not (0 <= check_y < height and 0 <= check_x < width):
                        move_blocked = True
                        break
                    if not traversable_mask[check_y, check_x]:
                        move_blocked = True
                        break

                if move_blocked:
                    continue

            neighbor_node = (neighbor_y, neighbor_x)

            obstacle_penalty = 0.0
            if obstacle_cost_map is not None:
                obstacle_penalty = float(obstacle_cost_map[neighbor_y, neighbor_x])

            new_cost = current_cost + move_cost + obstacle_penalty

            if (
                neighbor_node not in distance_map
                or new_cost < distance_map[neighbor_node]
            ):
                distance_map[neighbor_node] = new_cost
                parent_map[neighbor_node] = current_node
                heapq.heappush(priority_queue, (new_cost, neighbor_node))

    return reached_goal_paths


def shortest_path_to_any_goal(
    traversable: np.ndarray,
    start: Point,
    goal_mask: np.ndarray,
) -> Optional[List[Point]]:
    """
    Return the shortest path from start to any goal pixel.
    """
    goal_points = extract_goal_points(goal_mask)
    obstacle_cost_map = compute_obstacle_cost_map(traversable)

    paths = dijkstra_to_multiple_goals(
        traversable=traversable,
        start=start,
        goal_points=goal_points,
        return_all_paths=False,
        obstacle_cost_map=obstacle_cost_map,
    )
    if not paths:
        return None

    return next(iter(paths.values()))


def overlay_path(
    map_img: np.ndarray,
    path: List[Point],
    start: Optional[Point] = None,
    goals: Optional[List[Point]] = None,
    blocked_goals: Optional[List[Point]] = None,
    block_diameter: int = 75,
) -> np.ndarray:
    """
    Draw path, start, goals, and blocked goal regions on the image.

    Parameters
    ----------
    map_img : np.ndarray
    path : list[Point]
    start : optional Point
    goals : optional list[Point]
    blocked_goals : optional list[Point]
        Goals where suppression circles were applied
    block_diameter : int
        Diameter of suppression circles
    """
    if map_img.ndim == 2:
        vis = cv2.cvtColor(map_img, cv2.COLOR_GRAY2BGR)
    else:
        vis = map_img.copy()

    overlay = vis.copy()
    alpha = 0.3
    radius = block_diameter // 2

    if blocked_goals is not None:
        for goal_y, goal_x in blocked_goals:
            cv2.circle(
                overlay,
                (goal_x, goal_y),
                radius,
                (0, 255, 255),
                thickness=-1,
            )

        vis = cv2.addWeighted(overlay, alpha, vis, 1 - alpha, 0)

    for i in range(1, len(path)):
        point_a = (path[i - 1][1], path[i - 1][0])
        point_b = (path[i][1], path[i][0])
        cv2.line(vis, point_a, point_b, (0, 0, 255), 1)

    if start is not None:
        cv2.circle(vis, (start[1], start[0]), 4, (0, 255, 0), -1)

    if goals is not None:
        for goal_y, goal_x in goals:
            cv2.circle(vis, (goal_x, goal_y), 1, (255, 0, 0), -1)

    return vis


def goal_mask_from_osmnx_graph(
    graph: nx.MultiDiGraph,
    bbox: BoundingBox,
    mask_height: int,
    mask_width: int,
) -> np.ndarray:
    """
    Create a binary goal mask from an OSMnx graph inside a bounding box.

    Parameters
    ----------
    graph : nx.MultiDiGraph
        OSMnx graph, typically in EPSG:4326.
    bbox : tuple[float, float, float, float]
        Bounding box as (min_x, min_y, max_x, max_y) in EPSG:3857.
    mask_height : int
        Output mask height in pixels.
    mask_width : int
        Output mask width in pixels.

    Returns
    -------
    np.ndarray
        Binary mask of shape (mask_height, mask_width), dtype=uint8.
        1 means graph edge present, 0 means background.
    """
    # Convert graph edges to GeoDataFrame
    edges_gdf = ox.convert.graph_to_gdfs(
        graph,
        nodes=False,
        edges=True,
        fill_edge_geometry=True,
    )

    if edges_gdf.crs is None:
        raise ValueError("edges_gdf has no CRS. The graph must have CRS metadata.")

    # Reproject graph edges to match the bbox CRS
    edges_gdf = edges_gdf.to_crs(epsg=3857)

    min_x, min_y, max_x, max_y = bbox

    bbox_polygon = box(min_x, min_y, max_x, max_y)
    bbox_gdf = gpd.GeoDataFrame(
        geometry=[bbox_polygon],
        crs=config.METRIC_EPSG,
    )

    # Exclude building_access edges
    if "building_access" in edges_gdf.columns:
        edges_gdf = edges_gdf[~edges_gdf["building_access"].fillna(False)]

    # Clip graph edges to bounding box
    clipped_edges = gpd.clip(edges_gdf, bbox_gdf)

    if clipped_edges.empty:
        return np.zeros((mask_height, mask_width), dtype=np.uint8)

    # Build affine transform for rasterization
    transform = from_bounds(
        west=min_x,
        south=min_y,
        east=max_x,
        north=max_y,
        width=mask_width,
        height=mask_height,
    )

    # Burn geometries into raster
    shapes = (
        (geometry, 1)
        for geometry in clipped_edges.geometry
        if geometry is not None and not geometry.is_empty
    )

    goal_mask = rasterize(
        shapes=shapes,
        out_shape=(mask_height, mask_width),
        transform=transform,
        fill=0,
        default_value=1,
        all_touched=True,
        dtype=np.uint8,
    )

    # Widen lines to 3 pixels
    kernel = np.ones((3, 3), dtype=np.uint8)
    goal_mask = cv2.dilate(goal_mask, kernel, iterations=1)

    return goal_mask


def test(G, map_img, bbox):
    # map_img = cv2.imread("start.png", cv2.IMREAD_GRAYSCALE)
    # goal_mask = cv2.imread("goal_mask.png", cv2.IMREAD_GRAYSCALE)
    goal_mask = goal_mask_from_osmnx_graph(G, bbox, mask_height=512, mask_width=512)

    # For debugging: save the goal mask image
    cv2.imwrite("goal_mask.png", goal_mask)

    traversable = build_traversable_mask(
        map_img,
        threshold=98,
        free_is_dark=True,
        erode_obstacles=2,
    )

    obstacle_cost_map = compute_obstacle_cost_map(traversable, 5)

    start = find_center_free_cell(traversable)

    # path = shortest_path_to_any_goal(traversable, start, goal_mask)
    # if not path:
    #     print("No reachable goal found.")
    # else:
    #     vis = overlay_path(map_img, path, start=start)
    #     cv2.imwrite("path_debug.png", vis)

    goal_points = extract_goal_points(goal_mask)
    paths = dijkstra_to_multiple_goals(
        traversable,
        start,
        goal_points,
        obstacle_cost_map=obstacle_cost_map,
        goal_block_diameter=75,
    )

    blocked_goals = list(paths.keys())

    if not paths:
        print("No reachable goal found.")
    else:
        vis = map_img.copy()  # type: ignore
        for path in paths.values():
            vis = overlay_path(
                vis,
                path,
                start=start,
                goals=goal_points,
                blocked_goals=blocked_goals,
                block_diameter=75,
            )
        cv2.imwrite("path_debug.png", vis)
        print(paths)


def calc_2d_premise_paths(
    G: nx.MultiDiGraph,
    map_img: np.ndarray,
    bbox: BoundingBox,
    debug_img: bool = False,
) -> Dict[Point, List[Point]]:
    traversable = build_traversable_mask(
        map_img,
        threshold=config.TRAVERSABLE_THRESHOLD,
        free_is_dark=True,
        erode_obstacles=config.MINIMUM_OBSTACLE_DISTANCE,
    )
    start = find_center_free_cell(traversable)
    obstacle_cost_map = compute_obstacle_cost_map(
        traversable, config.GRADUAL_OBSTACLE_COST_RADIUS
    )

    goal_mask = goal_mask_from_osmnx_graph(
        G, bbox, mask_height=config.BBOX_SIZE, mask_width=config.BBOX_IMAGE_SIZE
    )
    goal_points = extract_goal_points(goal_mask)

    paths = dijkstra_to_multiple_goals(
        traversable,
        start,
        goal_points,
        obstacle_cost_map=obstacle_cost_map,
        goal_block_diameter=config.GOAL_BLOCK_DIAMETER,
    )

    # Debug visualization
    blocked_goals = list(paths.keys())
    vis = map_img.copy()  # type: ignore
    for path in paths.values():
        vis = overlay_path(
            vis,
            path,
            start=start,
            goals=goal_points,
            blocked_goals=blocked_goals,
            block_diameter=75,
        )

    if debug_img:
        cv2.imwrite("path_debug.png", vis)

    return paths


if __name__ == "__main__":
    test()
