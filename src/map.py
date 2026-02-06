"""
Everything related to drawing to the map and folium library is here.
"""

import math

import folium
import networkx as nx
import osmnx as ox

import config
import draw
import osm_gis

LEAFLET_STYLING = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        border-radius: 50%;
    }
    </style>
"""


def _add_tile_layers(m: folium.Map) -> None:
    # Fall back to OpenStreetMap when WMS layer is loading
    folium.TileLayer(
        tiles="openstreetmap", name=config.OPEN_STREET_MAP_LAYER_NAME
    ).add_to(m)

    # Add Seinäjoki satellite image WMS layer
    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="Hybridi-ilmakuva",
        transparent=True,
        fmt="image/png",
        name=config.SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME,
        overlay=False,
        show=True,
    ).add_to(m)

    # Add Seinäjoki topographic map WMS layer
    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="KantakartanMaastotiedot",
        transparent=True,
        fmt="image/png",
        name=config.SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME,
        overlay=True,
        show=True,
    ).add_to(m)


def make_buildings() -> folium.GeoJson:
    return folium.GeoJson(
        osm_gis.get_building_gdf(),
        name=config.BUILDING_LAYER_NAME,
        style_function=lambda _: {
            # "fillColor": "black",
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.2,
        },
    )


def make_roads(G: nx.MultiDiGraph) -> folium.GeoJson:
    max_log_centrality = math.log(
        max((val for _, _, val in G.edges(data="centrality") if val != 0))
    )
    # Decrement by 1 to remove the building itself.
    # The same building doesn't need paths to itself.
    buildings_num = len(
        [
            node
            for node, is_building_access in G.nodes(data="building_access")
            if is_building_access
        ]
    )
    building_access_num = buildings_num - 1
    min_log_centrality = math.log(building_access_num)

    def style(feature):
        # Use more red if the centrality is higher, and scale centrality to a log scale
        centrality = feature["properties"]["centrality"]
        # Use min centrality as the lower range
        if centrality <= building_access_num:
            log_centrality = min_log_centrality
        else:
            log_centrality = math.log(centrality)

        log_centrality_normalized = (log_centrality - min_log_centrality) / (
            max_log_centrality - min_log_centrality
        )

        # Set road style
        blue = int(0xFF * log_centrality_normalized)
        thickness = int(3 * log_centrality_normalized) + 2
        color = f"#0000{blue:02x}"
        return {
            "color": color,
            "weight": thickness,
            "opacity": 0.5,
        }

    return folium.GeoJson(
        ox.graph_to_gdfs(G, nodes=False),
        name=config.ROAD_LAYER_NAME,
        style_function=style,
    )


def build_map(G: nx.MultiDiGraph) -> folium.Map:
    m = folium.Map(
        location=config.START_LOCATION,
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

    # Construct map layers
    _add_tile_layers(m)
    make_buildings().add_to(m)
    make_roads(G).add_to(m)

    # Add draw plugin to the map
    draw.add_draw_plugin(m)

    # Custom CSS to style the edit vertices as circles
    m.get_root().header.add_child(folium.Element(LEAFLET_STYLING))

    return m
