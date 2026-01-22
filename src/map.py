import folium
from folium.plugins import Draw
import osmnx as ox

import config
import road_graph


def create_editable_road_layer() -> folium.FeatureGroup:
    editable_road_layer = folium.FeatureGroup(name=config.EDITABLE_ROAD_LAYER_NAME)

    osm_graph = road_graph.create_road_graph()
    # print(osm_graph.edges(keys=True, data=True))
    nodes, edges = ox.graph_to_gdfs(osm_graph)
    # print(edges.head())

    # Add edges and their metadata to the editable road layer
    for _, edge in edges.iterrows():
        # Make edge to geojson polyline and add to the layer
        geojson_polyline = folium.GeoJson(
            {
                "type": "Feature",
                "geometry": edge["geometry"].__geo_interface__,
                "properties": edge.drop("geometry").to_dict(),
            },
            style_function=lambda x: {"color": "blue"},
        )
        geojson_polyline.add_to(editable_road_layer)

    return editable_road_layer


def build_map() -> folium.Map:
    map = folium.Map(
        location=ox.geocode(config.PLACE_NAME),
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

    # Fall back to OpenStreetMap when WMS layer is loading
    folium.TileLayer(
        tiles="openstreetmap", name=config.OPEN_STREET_MAP_LAYER_NAME
    ).add_to(map)

    # Add Seinäjoki satellite image WMS layer
    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="Hybridi-ilmakuva",
        transparent=True,
        fmt="image/png",
        name=config.SEINAJOKI_SATELLITE_IMAGE_LAYER_NAME,
        overlay=False,
        show=True,
    ).add_to(map)

    # Add Seinäjoki topographic map WMS layer
    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="KantakartanMaastotiedot",
        transparent=True,
        fmt="image/png",
        name=config.SEINAJOKI_TOPOGRAPHIC_IMAGE_LAYER_NAME,
        overlay=True,
        show=True,
    ).add_to(map)

    # Add editable road layer to the map
    road_layer = create_editable_road_layer().add_to(map)
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
    ).add_to(map)

    # Add layer control to switch layers on and off
    folium.LayerControl().add_to(map)

    return map
