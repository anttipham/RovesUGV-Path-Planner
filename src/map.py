import folium
import osmnx as ox

PLACE_NAME = "Roves"


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

    # Add OSMnx graph data to the map
    graph = ox.graph.graph_from_place(
        PLACE_NAME,
        custom_filter='["foot"~"designated|yes"]',
    )
    # ox.save_graphml(graph, "graph.graphml")
    nodes, edges = ox.graph_to_gdfs(graph)
    folium.GeoJson(edges, name="Tiet").add_to(map)

    # Add layer control to switch layers on and off
    folium.LayerControl().add_to(map)

    return map
