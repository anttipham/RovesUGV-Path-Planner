"""
Configuration constants for the mapping application.
"""

import osmnx as ox
import shapely

# Streamlit constants
APP_TITLE = "RovesUGV"

# Tile names
OPEN_STREET_MAP_LAYER_NAME = "OpenStreetMap"
SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME = "Ilmakuva"
SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME = "Maastotiedot"

# Layer names
DRAW_LAYER_NAME = "Piirrokset"
BUILDING_LAYER_NAME = "Rakennukset"
ROAD_LAYER_NAME = "Tiet"
PATH_LAYER_NAME = "Reitti"

# OSMnx constants
TAGS_WAY = ["foot", "bicycle"]
for tag in TAGS_WAY:
    if tag not in ox.settings.useful_tags_way:
        ox.settings.useful_tags_way += [tag]
SIDEWALK_FOOT_TAG_VALUES = ["yes", "designated"]
MAP_EPSG = "EPSG:4326"
METRIC_EPSG = "EPSG:3857"

# Cost constants
COST_SIDEWALK = 0.015
COST_ROADWAY = 3

# 2D pathfinding constants
TRAVERSABLE_THRESHOLD = 98
GOAL_BLOCK_DIAMETER = 75
MINIMUM_OBSTACLE_DISTANCE = 2
GRADUAL_OBSTACLE_COST_RADIUS = 5
BBOX_SIZE = 1000
BBOX_IMAGE_SIZE = 512
SIMPLIFICATION_COMBINATION_TOLERANCE = 3
SIMPLIFICATION_LINE_TOLERANCE = 2

# Map features of Roves
START_LOCATION = (62.781708, 22.894071)
# MARKERS = {
#     "Heatmac Oy: Metal processing and coating": (62.7869635, 22.8749094),
#     "HANZA Mechanics Seinäjoki Oy: Metal machining": (62.7864375, 22.8780793),
#     "DB Schenker: Transport services": (62.7780027, 22.9230551),
#     "Würth: Small items": (62.7891151, 22.8584663),
#     "Puuilo Seinäjoki: Small items": (62.7901162, 22.8830035),
#     "ETRA Megacenter Seinäjoki: Packaging materials, etc.": (62.7882316, 22.8653514),
#     "Hartman Rauta: Supplies": (62.7886955, 22.8692573),
#     "Finnish Ore Oy: Metal sawing service": (62.7887869, 22.8708598),
# }
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
