"""
Map visualization and Folium layer construction.

Provides utilities to build interactive Folium maps with styled road/building layers,
WMS tile integration, and user-interaction handlers via the Draw plugin.
"""

import math

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
import rasterio
from folium.plugins import Draw
from rasterio.warp import transform_bounds

import config
import graph
import path

LEAFLET_STYLING = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        border-radius: 50%;
    }
    .leaflet-container {
        background: #000;
        outline: 0;
    }
    </style>
"""


def create_editable_road_layer() -> folium.FeatureGroup:
    """
    Create a feature group for user-drawn map interaction elements.

    Returns
    -------
    folium.FeatureGroup
        Empty editable layer attached to the Draw plugin.
    """
    editable_road_layer = folium.FeatureGroup(
        name=config.DRAW_LAYER_NAME,
        show=False,
        control=False,
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
    """
    Attach the Folium Draw plugin to the map for point-marker input.

    Parameters
    ----------
    m : folium.Map
        Map object to add the Draw plugin to.
    """
    # Add editable road layer to the map
    road_layer = create_editable_road_layer().add_to(m)
    Draw(
        export=False,
        filename="roves_ugv_map_data.geojson",
        feature_group=road_layer,
        draw_options={
            "marker": True,
            "polygon": {
                "shapeOptions": {
                    "color": "#ff0000",
                    "weight": 5,
                    "fillColor": "#ff6666",
                    "fillOpacity": 0.4,
                }
            },
            "polyline": False,
            "rectangle": False,
            "circle": False,
            "circlemarker": False,
        },
        edit_options={"edit": False, "remove": False},
    ).add_to(m)


def _add_tile_layers(m: folium.Map) -> None:
    """
    Add the local `mle_layout.tif` raster as the map background.

    Parameters
    ----------
    m : folium.Map
        Map object to add tile layers to.
    """
    with rasterio.open(config.MLE_LAYOUT_TIF_PATH) as src:
        raster_data = src.read()
        bounds = src.bounds
        src_crs = src.crs

    def to_uint8(channel: np.ndarray) -> np.ndarray:
        if channel.dtype == np.uint8:
            return channel
        channel = channel.astype(np.float32)
        min_val = float(np.nanmin(channel))
        max_val = float(np.nanmax(channel))
        if max_val <= min_val:
            return np.zeros(channel.shape, dtype=np.uint8)
        scaled = (channel - min_val) / (max_val - min_val)
        return (scaled * 255).astype(np.uint8)

    if raster_data.shape[0] >= 3:
        image = np.dstack(
            [
                to_uint8(raster_data[0]),
                to_uint8(raster_data[1]),
                to_uint8(raster_data[2]),
            ]
        )
    else:
        gray = to_uint8(raster_data[0])
        image = np.dstack([gray, gray, gray])

    west, south, east, north = bounds.left, bounds.bottom, bounds.right, bounds.top
    if src_crs and str(src_crs) != config.MAP_EPSG:
        west, south, east, north = transform_bounds(
            src_crs,
            config.MAP_EPSG,
            west,
            south,
            east,
            north,
        )

    folium.raster_layers.ImageOverlay(
        image=image,
        bounds=[[south, west], [north, east]],
        name="MLE Layout",
        opacity=1.0,
        interactive=False,
        cross_origin=False,
        zindex=1,
        show=True,
    ).add_to(m)


def make_buildings(G: nx.MultiDiGraph) -> folium.GeoJson:
    """
    Build a GeoJson layer displaying building polygons.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph containing building data.

    Returns
    -------
    folium.GeoJson
        GeoJson layer with building features.
    """
    if "ugv_buildings" not in G.graph:
        # Return an empty layer if there are no buildings to display
        return folium.GeoJson(gpd.GeoDataFrame(geometry=[], crs=config.MAP_EPSG))
    return folium.GeoJson(
        G.graph["ugv_buildings"],
        style_function=lambda _: {
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.2,
        },
    )


def make_roads(G: nx.MultiDiGraph) -> folium.GeoJson:
    """
    Build a styled road layer where line color and thickness reflect edge centrality.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph with centrality attributes.

    Returns
    -------
    folium.GeoJson
        Styled GeoJson road layer.
    """
    color_map = plt.get_cmap("Reds")
    max_log_centrality = (
        math.log2(G.graph["ugv_max_centrality"])
        if G.graph["ugv_max_centrality"] > 0
        else 0
    )

    # Set minimum log centrality to be the log of the number of building accesses
    buildings_num = len(
        [
            node
            for node, is_ugv_building_access in G.nodes(data="ugv_building_access")
            if is_ugv_building_access
        ]
    )
    # The same building doesn't need paths to itself.
    # Decrement by 1 to remove the building itself.
    building_access_num = buildings_num - 1
    min_log_centrality = (
        math.log2(building_access_num) if building_access_num > 0 else 0
    )

    def style(feature):
        centrality = feature["properties"]["ugv_centrality"]

        if centrality <= building_access_num:
            # Use min centrality as the lower range
            log_centrality = min_log_centrality
        else:
            # Scale centrality to log scale
            log_centrality = math.log2(centrality) if centrality > 0 else 0

        # Normalize log centrality to [0.0, 1.0] for color mapping
        log_centrality_normalized = (
            (log_centrality - min_log_centrality)
            / (max_log_centrality - min_log_centrality)
            if max_log_centrality > min_log_centrality
            else 0
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
        style_function=style,
    )


def make_crossings(G: nx.MultiDiGraph) -> folium.GeoJson:
    """
    Build a point layer for crossing nodes (debug visualization).

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph containing crossing nodes.

    Returns
    -------
    folium.GeoJson
        GeoJson layer with crossing points.
    """
    # Display nodes in map for debugging
    H = G.subgraph(
        [node for node, crossing in G.nodes(data="ugv_crossing") if crossing == True]
    )
    if H.number_of_nodes() == 0:
        # Return an empty layer if there are no crossings to display
        return folium.GeoJson(gpd.GeoDataFrame(geometry=[], crs=config.MAP_EPSG))

    gdf = ox.graph_to_gdfs(H, nodes=True, edges=False)
    return folium.GeoJson(
        gdf,
        marker=folium.CircleMarker(
            radius=2, color="black", fill=True, fill_opacity=0.7
        ),
    )


def make_intersections(G: nx.MultiDiGraph) -> folium.GeoJson:
    """
    Build a point layer for roadway intersections (debug visualization).

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph containing roadway intersections.

    Returns
    -------
    folium.GeoJson
        GeoJson layer with roadway intersection points.
    """
    # Display nodes in map for debugging
    H = G.subgraph(
        [
            node
            for node, intersection in G.nodes(data="ugv_intersection")
            if intersection == True
        ]
    )
    if H.number_of_nodes() == 0:
        # Return an empty layer if there are no intersections to display
        return folium.GeoJson(gpd.GeoDataFrame(geometry=[], crs=config.MAP_EPSG))

    gdf = ox.graph_to_gdfs(H, nodes=True, edges=False)
    return folium.GeoJson(
        gdf,
        marker=folium.CircleMarker(
            radius=3,
            weight=2,
            color="black",
            fill_color="red",
            fill_opacity=0.7,
        ),
    )


def build_map(G: nx.MultiDiGraph) -> folium.Map:
    """
    Assemble and return the full interactive Folium map.

    Combines tile layers, building/road overlays, crossing markers, and the Draw plugin.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph to visualize.

    Returns
    -------
    folium.Map
        Complete interactive map object.
    """
    m = folium.Map(
        location=config.START_LOCATION,
        tiles=None,
        zoom_start=14,
        attributionControl=False,
        crs="EPSG3857",
    )

    # Construct map layers
    _add_tile_layers(m)

    # Add draw plugin to the map
    add_draw_plugin(m)

    # Custom CSS to style the edit vertices as circles
    m.get_root().header.add_child(folium.Element(LEAFLET_STYLING))

    return m


def create_features(G: nx.MultiDiGraph) -> list[folium.FeatureGroup]:
    """
    Build a Folium layer showing all features

    Parameters
    ----------
    G : nx.MultiDiGraph
        Graph with computed paths and chosen buildings.

    Returns
    -------
    list[folium.FeatureGroup]
        List of feature groups containing all map features.
    """
    features = []

    # Show street network
    features.append(
        folium.FeatureGroup(name=config.ROAD_LAYER_NAME).add_child(make_roads(G))
    )
    # Show buildings
    features.append(
        folium.FeatureGroup(name=config.BUILDING_LAYER_NAME).add_child(
            make_buildings(G)
        )
    )
    # Show crossings
    features.append(
        folium.FeatureGroup(name=config.CROSSING_LAYER_NAME).add_child(
            make_crossings(G)
        )
    )
    # Show intersections
    features.append(
        folium.FeatureGroup(name=config.INTERSECTION_LAYER_NAME).add_child(
            make_intersections(G)
        )
    )

    # Show chosen buildings and the path between them
    building_path = folium.FeatureGroup(name=config.PATH_LAYER_NAME, control=True)
    ids = path.get_chosen_building_nodes(G)
    buildings = G.graph.get("ugv_buildings")
    if buildings:
        chosen_buildings = buildings[buildings.index.get_level_values("id").isin(ids)]
        folium.GeoJson(
            chosen_buildings,
            style_function=lambda _: {
                "fillColor": "#0095FF",
                "color": "black",
                "weight": 3,
                "fillOpacity": 0.4,
            },
        ).add_to(building_path)
        # Path requires a (1) source and (2) target node
        if len(ids) >= 2:
            # Show shortest path between buildings
            edges = G.graph["ugv_all_building_path_pairs"].get((ids[0], ids[1]), [])
            path_graph = G.edge_subgraph(edges)
            folium.GeoJson(
                ox.graph_to_gdfs(path_graph, nodes=False),
                style_function=lambda _: {
                    "color": "#007AD1",
                    "weight": 4,
                    "opacity": 1,
                },
            ).add_to(building_path)
        features.append(building_path)

    # Show user-drawn restricted zones
    restricted_zone_layer = folium.FeatureGroup(name=config.RESTRICTED_ZONES_LAYER_NAME)
    for metric_zone in G.graph["ugv_restricted_zones_metric"]:
        # Convert back to geographic coordinates for display
        zone = ox.projection.project_geometry(
            metric_zone, crs=config.METRIC_EPSG, to_crs=config.MAP_EPSG
        )[0]
        folium.GeoJson(
            zone,
            style_function=lambda _: {
                "color": "#ff0000",
                "weight": 3,
                "fillColor": "#ff6666",
                "fillOpacity": 0.4,
            },
            name=config.RESTRICTED_ZONES_LAYER_NAME,
        ).add_to(restricted_zone_layer)
    features.append(restricted_zone_layer)

    return features
