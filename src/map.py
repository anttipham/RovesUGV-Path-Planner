import folium
import osmnx as ox


def build_map_html() -> folium.Map:
    graph = ox.graph.graph_from_place("Roves", network_type="walk")
    m = folium.Map(
        location=ox.geocode("Roves"),
        tiles=None,
        zoom_start=13,
        attributionControl=False,
    )

    folium.TileLayer(tiles='openstreetmap', name='OpenStreetMap').add_to(m)

    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="Hybridi-ilmakuva",
        transparent=True,
        fmt="image/png",
        name="Ilmakuva",
        overlay=False,
        show=True,
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://kartat.seinajoki.fi/teklaogcweb/wms.ashx",
        layers="KantakartanMaastotiedot",
        transparent=True,
        fmt="image/png",
        name="Maastotiedot",
        overlay=True,
        show=True,
    ).add_to(m)

    nodes, edges = ox.graph_to_gdfs(graph)
    folium.GeoJson(edges, name="Tiet").add_to(m)

    folium.LayerControl().add_to(m)

    return m
