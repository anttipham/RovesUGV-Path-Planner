"""
Everything related to drawing to the map and folium library is here.
"""

import math

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from folium.plugins import Draw

import config
import draw
import graph

LEAFLET_STYLING = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        border-radius: 50%;
    }
    </style>
"""


def create_editable_road_layer() -> folium.FeatureGroup:
    editable_road_layer = folium.FeatureGroup(
        name=config.DRAW_LAYER_NAME,
    )
    edges = gpd.GeoDataFrame()

    # Add edges and their metadata to the editable road layer
    for _, edge in edges.iterrows():
        # Make edge to geojson polyline and add to the layer
        coords = [(y, x) for x, y in edge["geometry"].coords]
        folium.PolyLine(
            coords,
            color="blue",
        ).add_to(editable_road_layer)

    return editable_road_layer


def add_draw_plugin(m: folium.Map) -> None:
    # Add editable road layer to the map
    road_layer = create_editable_road_layer().add_to(m)
    Draw(
        export=False,
        filename="roves_ugv_map_data.geojson",
        feature_group=road_layer,
        draw_options={
            "polyline": False,
            "polygon": False,
            "rectangle": False,
            "circle": False,
            "marker": True,
            "circlemarker": False,
        },
        edit_options={"edit": False, "remove": False},
    ).add_to(m)


def _add_tile_layers(m: folium.Map) -> None:
    # OpenStreetMap
    folium.WmsTileLayer(
        url="http://localhost:8080/service",
        layers="osm",
        transparent=False,
        fmt="image/png",
        name=config.OPEN_STREET_MAP_LAYER_NAME,
        overlay=False,
        show=True,
    ).add_to(m)

    # Seinäjoki satellite image
    folium.WmsTileLayer(
        url="http://localhost:8080/service",
        layers="seinajoki_satellite_image",
        transparent=False,
        fmt="image/png",
        name=config.SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME,
        overlay=False,
        show=False,
    ).add_to(m)

    # Seinäjoki topographic map
    folium.WmsTileLayer(
        url="http://localhost:8080/service",
        layers="seinajoki_topographic_image",
        transparent=True,
        fmt="image/png",
        name=config.SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME,
        overlay=True,
        show=True,
    ).add_to(m)

    # TODO: Fall back to uncached versions of the WMS layers when the MapProxy is down.
    # # Fall back to OpenStreetMap when WMS layer is loading
    # folium.TileLayer(
    #     tiles="openstreetmap", name=config.OPEN_STREET_MAP_LAYER_NAME
    # ).add_to(m)

    # # Add Seinäjoki satellite image WMS layer
    # folium.WmsTileLayer(
    #     url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
    #     layers="Hybridi-ilmakuva",
    #     transparent=True,
    #     fmt="image/png",
    #     name=config.SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME,
    #     overlay=False,
    #     show=True,
    # ).add_to(m)

    # # Add Seinäjoki topographic map WMS layer
    # folium.WmsTileLayer(
    #     url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
    #     layers="KantakartanMaastotiedot",
    #     transparent=True,
    #     fmt="image/png",
    #     name=config.SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME,
    #     overlay=True,
    #     show=True,
    # ).add_to(m)


def make_buildings() -> folium.GeoJson:
    return folium.GeoJson(
        graph.get_building_gdf(),
        name=config.BUILDING_LAYER_NAME,
        style_function=lambda _: {
            # "fillColor": "black",
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.2,
        },
    )


def make_roads(G: nx.MultiDiGraph) -> folium.GeoJson:
    color_map = plt.get_cmap("Reds")
    max_log_centrality = math.log2(G.graph["max_centrality"])

    # Set minimum log centrality to be the log of the number of building accesses
    buildings_num = len(
        [
            node
            for node, is_ugv_closest_node_connection in G.nodes(
                data="ugv_closest_node_connection"
            )
            if is_ugv_closest_node_connection
        ]
    )
    # The same building doesn't need paths to itself.
    # Decrement by 1 to remove the building itself.
    building_access_num = buildings_num - 1
    min_log_centrality = math.log2(building_access_num)

    def style(feature):
        centrality = feature["properties"]["centrality"]

        if centrality <= building_access_num:
            # Use min centrality as the lower range
            log_centrality = min_log_centrality
        else:
            # Scale centrality to log scale
            log_centrality = math.log2(centrality)

        # Normalize log centrality to [0.0, 1.0] for color mapping
        log_centrality_normalized = (log_centrality - min_log_centrality) / (
            max_log_centrality - min_log_centrality
        )

        # Set road style
        red, green, blue = color_map(log_centrality_normalized)[:3]
        thickness = int(3 * log_centrality_normalized) + 1
        color = f"#{int(red*255):02x}{int(green*255):02x}{int(blue*255):02x}"
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


def make_crossings(G: nx.MultiDiGraph) -> folium.GeoJson:
    # Display nodes in map for debugging
    H = G.subgraph(
        [node for node, crossing in G.nodes(data="ugv_crossing") if crossing == True]
    )
    gdf = ox.graph_to_gdfs(H, nodes=True, edges=False)
    return folium.GeoJson(
        gdf,
        name=config.CROSSINGS_LAYER_NAME,
        marker=folium.CircleMarker(
            radius=2, color="black", fill=True, fill_opacity=0.7
        ),
    )


def build_map(G: nx.MultiDiGraph) -> folium.Map:
    m = folium.Map(
        location=config.START_LOCATION,
        tiles=None,
        zoom_start=13,
        attributionControl=False,
        crs="EPSG3857",
    )

    # Construct map layers
    _add_tile_layers(m)
    make_buildings().add_to(m)
    make_roads(G).add_to(m)
    make_crossings(G).add_to(m)

    # Presentation markers
    # markers = {
    #     "Heatmac Oy: Metal processing and coating": (62.7869635, 22.8749094),
    #     "HANZA Mechanics Seinäjoki Oy: Metal machining": (62.7864375, 22.8780793),
    #     "DB Schenker: Transport services": (62.7780027, 22.9230551),
    #     "Würth: Small items": (62.7891151, 22.8584663),
    #     "Puuilo Seinäjoki: Small items": (62.7901162, 22.8830035),
    #     "ETRA Megacenter Seinäjoki: Packaging materials, etc.": (62.7882316, 22.8653514),
    #     "Hartman Rauta: Supplies": (62.7886955, 22.8692573),
    #     "Finnish Ore Oy: Metal sawing service": (62.7887869, 22.8708598),
    # }
    # markers = folium.FeatureGroup("Yritykset")
    # for name, coords in markers.items():
    #     node = ox.nearest_nodes(G, coords[1], coords[0])
    #     node_attr = G.nodes[node]
    #     folium.Marker((node_attr["y"], node_attr["x"]), tooltip=name).add_to(markers)
    # markers.add_to(m)

    # Add draw plugin to the map
    add_draw_plugin(m)

    # Custom CSS to style the edit vertices as circles
    m.get_root().header.add_child(folium.Element(LEAFLET_STYLING))

    return m
