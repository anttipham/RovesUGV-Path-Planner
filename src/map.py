import folium
from folium.plugins import Draw
import osmnx as ox

import config
import road_graph

on_create = folium.JsCode(
    """
    (e) => {
        // Generate an id for the feature
        var feature = (e.layer.feature = e.layer.feature || {})
        feature.type = "Feature"
        feature.properties = feature.properties || {}
        feature.properties["id"] = Date.now();
    }
    """
)


def create_editable_road_layer() -> folium.FeatureGroup:
    editable_road_layer = folium.FeatureGroup(
        name=config.EDITABLE_ROAD_LAYER_NAME,
    )

    osm_graph = road_graph.create_road_graph()
    nodes, edges = ox.graph_to_gdfs(osm_graph)
    # print(nodes.head())
    # print(edges.head())

    # Add edges and their metadata to the editable road layer
    for _, edge in edges.iterrows():
        # Make edge to geojson polyline and add to the layer
        coords = [(y, x) for x, y in edge["geometry"].coords]
        folium.PolyLine(
            coords,
            color="blue",
        ).add_to(editable_road_layer)

    return editable_road_layer


def build_map() -> folium.Map:
    m = folium.Map(
        location=ox.geocode(config.PLACE_NAME),
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

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

    # Add editable road layer to the map
    road_layer = create_editable_road_layer().add_to(m)
    Draw(
        export=True,
        filename="roves_ugv_map_data.geojson",
        feature_group=road_layer,
        draw_options={
            "polyline": True,
            "polygon": True,
            "rectangle": False,
            "circle": False,
            "marker": True,
            "circlemarker": False,
        },
        on=handlers,
    ).add_to(m)

    # Add JavaScript events to Draw plugin
    handlers = {
        "draw:created": on_create,
    }
    m.on(**handlers)

    # Add layer control to switch layers on and off
    folium.LayerControl().add_to(m)

    return m
