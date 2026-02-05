import folium
import geopandas as gpd
import osmnx as ox
from folium.plugins import Draw

import config
import osm_gis

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
        name=config.DRAW_LAYER_NAME,
    )

    # TODO: Load a custom map of roads for editing access ways
    # osm_graph = osm_gis.create_road_graph()
    # nodes, edges = ox.graph_to_gdfs(osm_graph)
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
    # Add JavaScript events to Draw plugin
    handlers = {
        "draw:created": on_create,
    }
    m.on(**handlers)

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
    ).add_to(m)
