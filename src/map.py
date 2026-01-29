# import draw
import folium
import osmnx as ox
import networkx as nx
import math

import config
import osm_gis
import path

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


def make_buildings() -> folium.GeoJson:
    gdf = osm_gis.get_building_gdf()
    return folium.GeoJson(
        gdf,
        name=config.BUILDING_LAYER_NAME,
        style_function=lambda feature: {
            "fillColor": "gray",
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.5,
        },
    )


def make_roads(graph: nx.MultiDiGraph) -> folium.GeoJson:
    # TODO: visualisoi centrality jakauma
    max_log_centrality = math.log(
        max((val for _, _, val in graph.edges(data="centrality") if val != 0))
    )
    min_log_centrality = math.log(
        len(
            [
                node
                for node, is_building_access in graph.nodes(data="building_access")
                if is_building_access
            ]
        )
    )

    def style(feature):
        centrality = feature["properties"]["centrality"]
        if centrality <= 0:
            log_centrality = min_log_centrality
        else:
            log_centrality = math.log(centrality)
        log_centrality_normalized = (log_centrality - min_log_centrality) / (
            max_log_centrality - min_log_centrality
        )

        red = int(0xFF * log_centrality_normalized)
        blue = int(0xFF * (1 - log_centrality_normalized))
        thickness = int(4 * log_centrality_normalized) + 1
        return {
            "color": f"#{red:02x}10{blue:02x}",
            "weight": thickness,
            "opacity": 0.7,
        }

    return folium.GeoJson(
        ox.graph_to_gdfs(graph, nodes=False),
        name=config.ROAD_LAYER_NAME,
        style_function=style,
    )


def build_map() -> folium.Map:
    m = folium.Map(
        location=ox.geocode(config.PLACE_NAME),
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

    # Create graph
    graph = osm_gis.create_road_graph()
    path.add_weight(graph)
    path.add_centrality(graph)

    # Construct map layers
    add_tile_layers(m)
    make_buildings().add_to(m)
    make_roads(graph).add_to(m)

    # # Add draw plugin to the map
    # draw.add_draw_plugin(m)

    # Add layer control to switch layers on and off
    folium.LayerControl().add_to(m)

    # Custom CSS to style the edit vertices as circles
    m.get_root().header.add_child(folium.Element(LEAFLET_STYLING))

    return m
