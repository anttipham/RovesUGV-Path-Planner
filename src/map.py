import folium
from folium.plugins import Draw
import osmnx as ox

PLACE_NAME = "Roves"


def create_editable_road_layer() -> folium.FeatureGroup:
    # Add OSMnx graph data to draw plugin
    editable_road_layer = folium.FeatureGroup(name="Tieverkko")
    osm_graph = ox.graph.graph_from_place(
        PLACE_NAME,
        custom_filter='["foot"~"designated|yes"]',
    )
    nodes, edges = ox.graph_to_gdfs(osm_graph)
    # Loop edges to add them to the map
    for _, edge in edges.iterrows():
        coords = [(y, x) for x, y in edge["geometry"].coords]
        folium.PolyLine(
            coords,
            color="blue",
        ).add_to(editable_road_layer)

    return editable_road_layer


def build_map() -> folium.Map:
    map = folium.Map(
        location=ox.geocode(PLACE_NAME),
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

    # Fall back to OpenStreetMap when WMS layer is loading
    folium.TileLayer(tiles="openstreetmap", name="OpenStreetMap").add_to(map)

    # Add Seinäjoki satellite image WMS layer
    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="Hybridi-ilmakuva",
        transparent=True,
        fmt="image/png",
        name="Ilmakuva",
        overlay=False,
        show=True,
    ).add_to(map)

    # Add Seinäjoki topographic map WMS layer
    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="KantakartanMaastotiedot",
        transparent=True,
        fmt="image/png",
        name="Maastotiedot",
        overlay=True,
        show=True,
    ).add_to(map)

    # Add editable road layer to the map
    road_layer = create_editable_road_layer().add_to(map)
    Draw(
        export=True,
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
