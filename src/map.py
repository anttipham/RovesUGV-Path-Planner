import draw
import folium
import osmnx as ox

import config
import osm_gis

LEAFLET_STYLING = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        border-radius: 50%;
    }
    </style>
"""


def add_tile_layers(m: folium.Map) -> None:
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


def add_buildings(m: folium.Map) -> None:
    gdf = osm_gis.get_building_gdf()
    folium.GeoJson(
        gdf,
        name=config.BUILDING_LAYER_NAME,
        style_function=lambda feature: {
            "fillColor": "gray",
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.5,
        },
    ).add_to(m)


def add_roads(m: folium.Map) -> None:
    graph = osm_gis.create_road_graph_gdf()
    folium.GeoJson(
        ox.graph_to_gdfs(graph, nodes=False),
        name=config.ROAD_LAYER_NAME,
        style_function=lambda feature: {
            "color": "blue",
            "weight": 2,
            "opacity": 0.7,
        },
    ).add_to(m)
    return graph


def build_map() -> folium.Map:
    m = folium.Map(
        location=ox.geocode(config.PLACE_NAME),
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

    # Construct map layers
    add_tile_layers(m)
    add_buildings(m)
    add_roads(m)

    # Add draw plugin to the map
    draw.add_draw_plugin(m)

    # Add layer control to switch layers on and off
    folium.LayerControl().add_to(m)

    # Custom CSS to style the edit vertices as circles
    m.get_root().header.add_child(folium.Element(LEAFLET_STYLING))

    return m
