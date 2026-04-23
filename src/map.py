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
import osmnx as ox
from folium.plugins import Draw

import config
import graph
import path

LEAFLET_STYLING = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        border-radius: 50%;
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
    Add base and overlay WMS tile layers to the map.

    Includes OpenStreetMap, satellite imagery, and topographic layers from MapProxy.

    Parameters
    ----------
    m : folium.Map
        Map object to add tile layers to.
    """
    # OpenStreetMap
    folium.WmsTileLayer(
        url="http://localhost:8080/service",
        layers="osm",
        transparent=False,
        fmt="image/png",
        name=config.OPEN_STREET_MAP_LAYER_NAME,
        overlay=False,
        show=False,
    ).add_to(m)

    # Seinäjoki satellite image
    folium.WmsTileLayer(
        url="http://localhost:8080/service",
        layers="seinajoki_satellite_image",
        transparent=False,
        fmt="image/png",
        name=config.SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME,
        overlay=False,
        show=True,
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

    # Debug: Fall back to uncached versions of the WMS layers when the MapProxy is down.
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
    max_log_centrality = math.log2(G.graph["ugv_max_centrality"])

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
    min_log_centrality = math.log2(building_access_num)

    def style(feature):
        centrality = feature["properties"]["ugv_centrality"]

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
    gdf = ox.graph_to_gdfs(H, nodes=True, edges=False)
    return folium.GeoJson(
        gdf,
        marker=folium.CircleMarker(
            radius=2, color="black", fill=True, fill_opacity=0.7
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
        zoom_start=13,
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

    # Show street network and buildings
    features.append(
        folium.FeatureGroup(name=config.ROAD_LAYER_NAME).add_child(make_roads(G))
    )
    features.append(
        folium.FeatureGroup(name=config.BUILDING_LAYER_NAME).add_child(
            make_buildings(G)
        )
    )
    features.append(
        folium.FeatureGroup(name=config.CROSSING_LAYER_NAME).add_child(
            make_crossings(G)
        )
    )

    # Show chosen buildings and the path between them
    building_path = folium.FeatureGroup(name=config.PATH_LAYER_NAME, control=True)
    ids = path.get_chosen_building_nodes(G)
    buildings = G.graph["ugv_buildings"]
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
