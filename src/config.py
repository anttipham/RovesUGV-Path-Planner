"""
Configuration constants for the mapping application.
"""

import osmnx as ox

# Streamlit constants
APP_TITLE = "UGV Roves"

# OSMnx constants
PLACE_NAME = "Roves"
TAGS_WAY = ["foot", "bicycle"]
for tag in TAGS_WAY:
    if tag not in ox.settings.useful_tags_way:
        ox.settings.useful_tags_way += [tag]

# Tile names
OPEN_STREET_MAP_LAYER_NAME = "OpenStreetMap"
SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME = "Ilmakuva"
SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME = "Maastotiedot"

# Layer names
DRAW_LAYER_NAME = "Piirrokset"
BUILDING_LAYER_NAME = "Rakennukset"
ROAD_LAYER_NAME = "Tiet"
PATH_LAYER_NAME = "Reitti"
