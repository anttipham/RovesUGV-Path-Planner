"""
Configuration constants for the RovesUGV Path Planner application.

This module centralizes all routing parameters, UI labels, coordinate system definitions,
and 2D raster pathfinding settings used throughout the application.
"""

import osmnx as ox
import shapely
from pathlib import Path

# Streamlit constants
APP_TITLE = "RovesUGV Path Planner"

# Local data files
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE_NETWORK_GEOJSON_PATH = PROJECT_ROOT / "data" / "warehousenetwork.geojson"
MLE_LAYOUT_TIF_PATH = PROJECT_ROOT / "data" / "mle_layout_canvasedit.tif"

# Tile names
OPEN_STREET_MAP_LAYER_NAME = "OpenStreetMap"
SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME = "Ilmakuva"
SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME = "Maastotiedot"

# Layer names
DRAW_LAYER_NAME = "Piirtotaso"
BUILDING_LAYER_NAME = "Rakennukset"
ROAD_LAYER_NAME = "Tiet"
PATH_LAYER_NAME = "Reitti"
CROSSING_LAYER_NAME = "Tienylitykset"
INTERSECTION_LAYER_NAME = "Risteykset"
RESTRICTED_ZONES_LAYER_NAME = "Rajoitetut alueet"

# OSMnx constants
TAGS_WAY = ["foot", "bicycle"]
for tag in TAGS_WAY:
    if tag not in ox.settings.useful_tags_way:
        ox.settings.useful_tags_way += [tag]
SIDEWALK_FOOT_TAG_VALUES = ["yes", "designated"]
MAP_EPSG = "EPSG:4326"  # WGS84 geographic CRS
METRIC_EPSG = "EPSG:3857"  # Web Mercator projected CRS (meters)

# Cost constants for routing
COST_SIDEWALK = 0.008  # Cost per meter on sidewalk
COST_ROADWAY = 5 * COST_SIDEWALK  # Cost per meter on roadway
COST_TRAFFIC_SIGNALS = 0  # Additional cost at traffic-signal crossings
COST_ZEBRA_CROSSING = 2  # Additional cost at zebra/marked crossings
COST_UNCONTROLLED_CROSSING = 5  # Additional cost at uncontrolled crossings
COST_ROADWAY_CROSSING = 30  # Penalty for exiting a crossing onto a roadway
COST_CENTRALITY_FACTOR = 0.0  # Multiplier for edge centrality penalty (0 = disabled)
CENTRALITY_ITERATION_LIMIT = 100  # Max iteration limit for the backbone calculation

# 2D raster pathfinding constants
GRADUAL_OBSTACLE_COST_RADIUS = (
    4  # Max distance (pixels) for soft obstacle penalty rings
)
SIMPLIFICATION_COMBINATION_TOLERANCE = 3  # Distance (pixels) for path merging
SIMPLIFICATION_LINE_TOLERANCE = 3  # Tolerance for LineString.simplify()

TRAVERSABLE_THRESHOLD = (
    98  # Grayscale threshold to distinguish free space from obstacles
)
GOAL_BLOCK_DIAMETER = 75  # Diameter (pixels) of suppression circle around reached goals
MINIMUM_OBSTACLE_DISTANCE = 2  # Dilation radius (pixels) for obstacle safety margin
BBOX_SIZE = 1000  # Size (meters) of bounding box around clicked point
BBOX_IMAGE_SIZE = 512  # Resolution (pixels) of downloaded raster tiles

# Map features of Roves area
START_LOCATION = (62.796544, 22.974043)  # in EPSG:4326
AREA_POLYGON = shapely.Polygon(
    (
        (22.877596, 62.77948),
        (22.876958, 62.779794),
        (22.873106, 62.781747),
        (22.866486, 62.78502),
        (22.86315, 62.786615),
        (22.856433, 62.789088),
        (22.859035, 62.789696),
        (22.86014, 62.789912),
        (22.865655, 62.790935),
        (22.869941, 62.791536),
        (22.871963, 62.791793),
        (22.876271, 62.792438),
        (22.877773, 62.792414),
        (22.87839, 62.792352),
        (22.878878, 62.792399),
        (22.879624, 62.792561),
        (22.880407, 62.79275),
        (22.880584, 62.792767),
        (22.882365, 62.79219),
        (22.88317, 62.791957),
        (22.88619, 62.7913),
        (22.892455, 62.790069),
        (22.898979, 62.788803),
        (22.90268, 62.787952),
        (22.902879, 62.787648),
        (22.903935, 62.787469),
        (22.9054, 62.787542),
        (22.91173, 62.786303),
        (22.917759, 62.785121),
        (22.924486, 62.783848),
        (22.925023, 62.783762),
        (22.930076, 62.782741),
        (22.930816, 62.78239),
        (22.930913, 62.781794),
        (22.931691, 62.780898),
        (22.932463, 62.779838),
        (22.932469, 62.777753),
        (22.93234, 62.775824),
        (22.931803, 62.773453),
        (22.931696, 62.771985),
        (22.931707, 62.769884),
        (22.931739, 62.767238),
        (22.931771, 62.766094),
        (22.932039, 62.764454),
        (22.931256, 62.763993),
        (22.926729, 62.762397),
        (22.923902, 62.763207),
        (22.921439, 62.763939),
        (22.918076, 62.764923),
        (22.916011, 62.765476),
        (22.912502, 62.766546),
        (22.908876, 62.767624),
        (22.904021, 62.769047),
        (22.896978, 62.771092),
        (22.890337, 62.773109),
        (22.88641, 62.774931),
        (22.882193, 62.777031),
        (22.877596, 62.77948),
    )
)
